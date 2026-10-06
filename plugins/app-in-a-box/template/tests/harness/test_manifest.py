"""Pin the harness manifest to reality, on every PR.

`.claude/harness/manifest.json` says which components are protected and which hooks
MUST be wired. `.claude/hooks/harness-healthcheck.py` checks that at session start,
which has one blind spot: it only runs when someone opens a session. A PR that renames
a protected hook, drops a required hook from settings.json, or deletes a protected
skill merges clean and is found days later. These are the repo-state subset of the
healthcheck, run where the change lands, measured the same way (a substring test on
the serialized settings) so the test and the sensor can't disagree.

Plus the Codex half: `.codex/hooks.json` is generated from the same settings, so it
must wire the same scripts and must not reference `$CLAUDE_PROJECT_DIR` (Codex never
sets it, so the hook would run `/.claude/hooks/x` and fail silently).

Plus the wrapper: every hook command checks its script EXISTS before running it. When a
worktree is moved or deleted under a live session, `bash "$CLAUDE_PROJECT_DIR/..."` dies
with exit 127 on every call, which Claude Code reports nowhere, and a safety hook that
dies is a safety hook that is OFF. The wrapper falls back to `git rev-parse
--show-toplevel`, then says so in a `systemMessage` and exits 0.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import warnings
from pathlib import Path
from typing import Any

import pytest
from harness_lib import AGENTS_DIR, HOOKS_DIR, MANIFEST, ROOT, SETTINGS, load_json

PROTECTED_GROUPS = ("protected_hooks", "protected_skills", "protected_agents")
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
HOOK_REF = re.compile(r"hooks/([\w.-]+\.(?:sh|py))")
INTERPRETERS = ("bash", "python3", "node", "sh")
# The guarded shape every hook command must have. `name` is the script; the message
# must say the hook is OFF so the session knows a guard is missing, and `exit 0` keeps
# a missing hook from blocking the tool call (the hook is gone; the work isn't).
WRAPPER_RE = re.compile(
    r'^f="\$CLAUDE_PROJECT_DIR/\.claude/hooks/(?P<name>[\w.-]+)"; '
    r'\[ -f "\$f" \] \|\| f="\$\(git rev-parse --show-toplevel 2>/dev/null\)/\.claude/hooks/(?P=name)"; '
    r'\[ -f "\$f" \] \|\| \{ printf \'\{"systemMessage":"hook (?P=name) is OFF[^\']*\'; exit 0; \}; '
    r"(?P<interp>" + "|".join(INTERPRETERS) + r') "\$f"( .*)?$'
)


def protected_files(manifest: dict[str, Any]) -> list[str]:
    return [it["file"] for g in PROTECTED_GROUPS for it in manifest.get(g, []) if it.get("file")]


def manifest_problems(manifest: dict[str, Any], settings: dict[str, Any], exists) -> list[str]:
    """Pure core: `exists(relpath) -> bool` so a negative control can drive it."""
    problems = []
    blob = json.dumps(settings)
    for f in protected_files(manifest):
        if not exists(f):
            problems.append(f"protected component missing on disk: {f}")
    for name in manifest.get("registered_hook_check", {}).get("must_be_registered", []):
        if name not in blob:
            problems.append(f"required hook not registered in .claude/settings.json: {name}")
    for name in sorted(set(HOOK_REF.findall(blob))):
        if not exists(f".claude/hooks/{name}"):
            problems.append(f"settings.json wires a hook that is not on disk: {name}")
    return problems


def codex_hook_problems(settings: dict[str, Any], codex: dict[str, Any]) -> list[str]:
    problems = []
    claude_scripts = set(HOOK_REF.findall(json.dumps(settings.get("hooks", {}))))
    codex_blob = json.dumps(codex.get("hooks", {}))
    codex_scripts = set(HOOK_REF.findall(codex_blob))
    if claude_scripts != codex_scripts:
        problems.append(
            f"Codex hooks {sorted(codex_scripts)} != Claude hooks {sorted(claude_scripts)}"
        )
    if "CLAUDE_PROJECT_DIR" in codex_blob:
        problems.append("Codex hooks reference $CLAUDE_PROJECT_DIR, which Codex never sets")
    if set(settings.get("hooks", {})) != set(codex.get("hooks", {})):
        problems.append("Codex hook events differ from Claude's")
    return problems


def hook_command_problems(cmd: str) -> list[str]:
    """Pure core for the wrapper rule. Empty list = guarded."""
    m = WRAPPER_RE.match(cmd)
    if m:
        return []
    if re.match(r"^(" + "|".join(INTERPRETERS) + r") ", cmd):
        return [
            "hook command has no existence check (a moved or deleted worktree kills it with "
            f"exit 127, silently): {cmd[:80]}"
        ]
    return [f"hook command is neither a bare interpreter call nor the guarded wrapper: {cmd[:80]}"]


def all_hook_commands(settings: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (event, h.get("command", ""))
        for event, groups in settings.get("hooks", {}).items()
        for g in groups
        for h in g.get("hooks", [])
    ]


def event_problems(manifest: dict[str, Any], settings: dict[str, Any]) -> list[str]:
    """Each protected hook's declared `event` must be where settings.json registers it.

    `event` is prose ("PostToolUse + UserPromptSubmit (async)"); its first token is the
    claim. "library" and "on-demand" make no registration claim and are skipped."""
    problems = []
    by_event = {ev: json.dumps(groups) for ev, groups in settings.get("hooks", {}).items()}
    for item in manifest.get("protected_hooks", []):
        ev = str(item.get("event", ""))
        m = re.match(r"[A-Za-z]+", ev)
        if not m or m.group(0) in ("library", "on"):
            continue
        name = os.path.basename(str(item.get("file", "")))
        if name not in by_event.get(m.group(0), ""):
            problems.append(
                f"{name}: manifest says `{ev}` but settings.json does not register it under "
                f"{m.group(0)}"
            )
    return problems


def _exists(relpath: str) -> bool:
    return (ROOT / relpath).exists()


def test_manifest_and_settings_parse() -> None:
    assert load_json(MANIFEST).get("version") == 1
    assert "hooks" in load_json(SETTINGS)


def test_there_are_protected_components() -> None:
    assert protected_files(load_json(MANIFEST)), "manifest protects nothing"


def test_manifest_matches_the_repo() -> None:
    problems = manifest_problems(load_json(MANIFEST), load_json(SETTINGS), _exists)
    assert not problems, "\n".join(problems)


def test_codex_hooks_mirror_claude_hooks() -> None:
    assert CODEX_HOOKS.exists(), ".codex/hooks.json missing: re-run render.py --adapters-only"
    problems = codex_hook_problems(load_json(SETTINGS), load_json(CODEX_HOOKS))
    assert not problems, "\n".join(problems) + " (re-run render.py --adapters-only)"


def test_path_rules_present() -> None:
    rules = [p for p in (AGENTS_DIR / "rules").glob("*.md") if p.name != "README.md"]
    assert rules, ".agents/rules/ is empty: inject-path-rules.py has nothing to inject"


def test_every_hook_command_is_the_guarded_wrapper() -> None:
    """Every command runs its script via an interpreter (no exec bit needed) AFTER
    checking the file exists, and the wrapper names the same script three times."""
    problems = [
        p for _, cmd in all_hook_commands(load_json(SETTINGS)) for p in hook_command_problems(cmd)
    ]
    assert not problems, "\n".join(problems)


def test_protected_hook_events_match_registration() -> None:
    assert event_problems(load_json(MANIFEST), load_json(SETTINGS)) == []


def _run_wrapper(cmd: str, project_dir: Path, cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir), "GIT_DIR": str(cwd / "nogit")}
    return subprocess.run(
        ["bash", "-c", cmd],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=60,
    )


def _hook_id(cmd: str) -> str:
    m = WRAPPER_RE.match(cmd)
    return m.group("name") if m else "?"


@pytest.mark.parametrize(
    "cmd", [c for _, c in all_hook_commands(load_json(SETTINGS))], ids=_hook_id
)
def test_wrapper_reports_a_missing_hook_and_exits_zero(cmd: str, tmp_path: Path) -> None:
    """The failure the wrapper exists for: project dir gone, git unusable. It must say
    which hook is OFF (stdout, as a systemMessage) and exit 0, never 127."""
    out = _run_wrapper(cmd, tmp_path / "gone", tmp_path)
    m = WRAPPER_RE.match(cmd)
    assert m is not None
    assert out.returncode == 0, out.stderr
    assert '"systemMessage"' in out.stdout
    assert m.group("name") in out.stdout
    assert "OFF" in out.stdout


def test_wrapper_runs_the_hook_when_present(tmp_path: Path) -> None:
    """Positive control: with a live project dir the same command runs the real hook."""
    cmd = next(c for ev, c in all_hook_commands(load_json(SETTINGS)) if "session-start.sh" in c)
    out = _run_wrapper(cmd, ROOT, tmp_path)
    assert (
        out.returncode == 0
    )
    assert (
        "Session start" in out.stdout
    )
    assert (
        "systemMessage" not in out.stdout
    )


def over_budget(actual: dict[str, int], limits: dict[str, int]) -> list[str]:
    return [f"{k} {actual[k]}/{limits[k]}" for k in actual if k in limits and actual[k] > limits[k]]


def test_complexity_budget_is_an_alarm_not_a_gate() -> None:
    """Over budget WARNS, never fails: the manifest defines the budget as an accretion
    alarm that means harness-optimize owes a look, not a merge gate."""
    limits = load_json(MANIFEST).get("complexity_budget", {}).get("limits", {})
    blob = json.dumps(load_json(SETTINGS))
    actual = {
        "rules": len([p for p in (AGENTS_DIR / "rules").glob("*.md") if p.name != "README.md"]),
        "registered_hooks": len(set(HOOK_REF.findall(blob))),
        "skills": len(list((AGENTS_DIR / "skills").glob("*/SKILL.md"))),
        "agents": len(list((AGENTS_DIR / "agents").glob("*.md"))),
    }
    over = over_budget(actual, limits)
    if over:
        warnings.warn(f"complexity budget exceeded: {', '.join(over)}", UserWarning, stacklevel=1)
    assert HOOKS_DIR.is_dir()


# ---- negative controls --------------------------------------------------------

MANIFEST_OK = {
    "protected_hooks": [{"file": ".claude/hooks/a.sh"}],
    "registered_hook_check": {"must_be_registered": ["a.sh"]},
}
SETTINGS_OK = {
    "hooks": {"Stop": [{"hooks": [{"command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/a.sh"'}]}]}
}


def test_clean_manifest_passes() -> None:
    assert manifest_problems(MANIFEST_OK, SETTINGS_OK, lambda f: True) == []


def test_deleted_protected_component_fails() -> None:
    problems = manifest_problems(MANIFEST_OK, SETTINGS_OK, lambda f: False)
    assert any("protected component missing" in p for p in problems)
    assert any("not on disk" in p for p in problems)


def test_unregistered_required_hook_fails() -> None:
    problems = manifest_problems(MANIFEST_OK, {"hooks": {}}, lambda f: True)
    assert problems == ["required hook not registered in .claude/settings.json: a.sh"]


def test_codex_drift_fails() -> None:
    good = {"hooks": {"Stop": [{"hooks": [{"command": 'bash "$(git)/.claude/hooks/a.sh"'}]}]}}
    assert codex_hook_problems(SETTINGS_OK, good) == []
    assert any("!=" in p for p in codex_hook_problems(SETTINGS_OK, {"hooks": {"Stop": []}}))
    assert any("CLAUDE_PROJECT_DIR" in p for p in codex_hook_problems(SETTINGS_OK, SETTINGS_OK))


def test_budget_alarm_fires() -> None:
    assert over_budget({"skills": 15, "rules": 2}, {"skills": 14, "rules": 9}) == ["skills 15/14"]
    assert over_budget({"skills": 14}, {"skills": 14}) == []


WRAPPED = (
    'f="$CLAUDE_PROJECT_DIR/.claude/hooks/a.sh"; [ -f "$f" ] || f="$(git rev-parse --show-toplevel '
    '2>/dev/null)/.claude/hooks/a.sh"; [ -f "$f" ] || { printf \'{"systemMessage":"hook a.sh is '
    'OFF for this session: not found."}\\n\'; exit 0; }; bash "$f"'
)


def test_wrapper_rule_passes_the_guarded_shape_and_fails_the_rest() -> None:
    assert hook_command_problems(WRAPPED) == []
    assert hook_command_problems(WRAPPED + " --session") == []
    assert any(
        "no existence check" in p
        for p in hook_command_problems('bash "$CLAUDE_PROJECT_DIR/.claude/hooks/a.sh"')
    )
    # The three names must agree: a wrapper that checks a.sh but runs b.sh guards nothing.
    assert hook_command_problems(WRAPPED.replace('hooks/a.sh"; [ -f', 'hooks/b.sh"; [ -f', 1))
    # Dropping `exit 0` turns "hook OFF" into "every tool call blocked".
    assert hook_command_problems(WRAPPED.replace("; exit 0; }", "; }"))
    assert hook_command_problems(WRAPPED.replace("is OFF", "is fine"))


def test_event_rule_can_fail() -> None:
    manifest = {
        "protected_hooks": [
            {"file": ".claude/hooks/a.sh", "event": "Stop"},
            {"file": ".claude/hooks/lib.py", "event": "library (imported)"},
            {"file": ".claude/hooks/x.py", "event": "on-demand"},
        ]
    }
    assert event_problems(manifest, SETTINGS_OK) == []
    moved = {"hooks": {"PreToolUse": SETTINGS_OK["hooks"]["Stop"]}}
    assert event_problems(manifest, moved) == [
        "a.sh: manifest says `Stop` but settings.json does not register it under Stop"
    ]
