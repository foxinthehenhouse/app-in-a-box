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
"""

from __future__ import annotations

import json
import re
import warnings
from typing import Any

from harness_lib import AGENTS_DIR, HOOKS_DIR, MANIFEST, ROOT, SETTINGS, load_json

PROTECTED_GROUPS = ("protected_hooks", "protected_skills", "protected_agents")
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
HOOK_REF = re.compile(r"hooks/([\w.-]+\.(?:sh|py))")


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


def test_hook_scripts_are_executable_or_invoked_via_interpreter() -> None:
    """settings.json runs every hook as `bash x.sh` / `python3 x.py`, so no exec bit is
    needed. A bare path (no interpreter) would need +x; flag it before it fails."""
    for group in load_json(SETTINGS).get("hooks", {}).values():
        for g in group:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                assert re.match(
                    r"^(bash|python3|node|sh) ", cmd
                ), f"hook without interpreter: {cmd}"


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
