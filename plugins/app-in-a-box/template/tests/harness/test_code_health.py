"""Code health and drift: the guards that keep this repo honest as it grows.

  - generated files (tokens.ts, the Codex adapters) match their sources
    (scripts/check_generated.py, run by CI)
  - the PR title will make a good squash commit (scripts/check_pr_title.py, pr-title.yml)
  - CODEOWNERS keeps an owner on migrations, .github, .agents and auth
  - the dead-code and complexity gates stay on: knip in `npm run gates`, vulture in CI,
    ruff's C90/ASYNC/SIM/RET/PT, ESLint's complexity rules

Each rule is checked on the real repo AND shown to fail on a planted violation.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
import shutil
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from harness_lib import ROOT


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec
    assert spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _load("check_generated")
title = _load("check_pr_title")

# ---- generated files ---------------------------------------------------------------


def test_generated_files_are_current() -> None:
    problems = gen.stale(ROOT)
    assert not problems, "\n".join(problems) + "\nFix: python3 scripts/check_generated.py --fix"


def test_the_check_covers_tokens_and_every_adapter() -> None:
    want = gen.expected(ROOT)
    assert "mobile/lib/tokens.ts" in want
    assert {".codex/config.toml", ".codex/hooks.json"} <= set(want)
    roles = {p.stem for p in (ROOT / ".agents" / "agents").glob("*.md")}
    assert {f".codex/agents/{r}.toml" for r in roles} <= set(want)


def _mini_repo(tmp_path: Path) -> Path:
    for rel in ("design/tokens.json", ".mcp.json", ".claude/settings.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    shutil.copytree(ROOT / ".agents" / "agents", tmp_path / ".agents" / "agents")
    assert gen.fix(tmp_path)
    assert gen.stale(tmp_path) == []
    return tmp_path


def test_hand_edited_tokens_ts_is_caught(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path)
    ts = repo / "mobile" / "lib" / "tokens.ts"
    ts.write_text(ts.read_text().replace('"accent": "#', '"accent": "#0', 1))
    assert gen.stale(repo) == [
        "mobile/lib/tokens.ts: differs from what its source generates (hand-edited?)"
    ]


def test_stale_and_orphan_codex_roles_are_caught(tmp_path: Path) -> None:
    repo = _mini_repo(tmp_path)
    role = next((repo / ".agents" / "agents").glob("*.md"))
    role.write_text(role.read_text() + "\nOne more instruction.\n")
    (repo / ".codex" / "agents" / "gone.toml").write_text('name = "gone"\n')
    problems = gen.stale(repo)
    assert (
        f".codex/agents/{role.stem}.toml: differs from what its source generates (hand-edited?)"
        in problems
    )
    assert ".codex/agents/gone.toml: generated from a source that no longer exists" in problems


# ---- PR titles ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "good",
    [
        "feat: streak count on Home (#42)",
        "fix(auth): resend the sign-in code (APP-17)",
        "docs: draft the privacy policy",
        "chore: fix a typo [no-ticket]",
        'Revert "feat: streak count on Home (#42)"',
    ],
)
def test_good_titles_pass(good: str) -> None:
    assert title.problems(good) == []


@pytest.mark.parametrize(
    ("bad", "needle"),
    [
        ("Update api.ts", "must look like `<type>: <summary>`"),
        ("feature: streaks", "`feature` is not a type"),
        ("feat: WIP streaks", "WIP/draft marker"),
        ("[draft] feat: streaks", "must look like"),
        ("fix: the sign-in code.", "full stop"),
        ("chore: " + "x" * 70, "keep it to 72"),
        ("feat:streaks", "must look like"),
    ],
)
def test_bad_titles_fail(bad: str, needle: str) -> None:
    assert any(needle in p for p in title.problems(bad)), title.problems(bad)


def test_pr_title_workflow_runs_the_lint_on_every_pr() -> None:
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "pr-title.yml").read_text())
    on = wf.get("on", wf.get(True))
    assert {"opened", "edited", "synchronize"} <= set(on["pull_request"]["types"])
    runs = " ".join(str(s.get("run", "")) for s in wf["jobs"]["pr-title"]["steps"])
    assert "scripts/check_pr_title.py" in runs
    assert "${{" not in runs, "pass the title through env, never inline (shell injection)"


# ---- CODEOWNERS --------------------------------------------------------------------

# One real path per area that must always have an owner.
MUST_OWN = [
    "supabase/migrations/20250101000000_example.sql",
    ".github/workflows/ci.yml",
    ".github/CODEOWNERS",
    ".agents/skills/pr-review/SKILL.md",
    "backend/auth.py",
    "mobile/lib/auth.tsx",
    "mobile/app/(auth)/sign-in.tsx",
]


def _rules(text: str) -> list[tuple[str, list[str]]]:
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            pattern, *owners = line.split()
            out.append((pattern, owners))
    return out


def _matches(pattern: str, path: str) -> bool:
    """The subset of CODEOWNERS (gitignore) syntax this file uses: anchored paths,
    directories with a trailing slash, and globs."""
    anchored = pattern.startswith("/")
    pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        return path.startswith(pattern) if anchored else f"/{pattern}" in f"/{path}"
    return fnmatch.fnmatchcase(path, pattern) if anchored else path.endswith(pattern)


def owners_of(text: str, path: str) -> list[str]:
    """GitHub's rule: the LAST matching line wins, and a line with no owners un-owns."""
    found: list[str] = []
    for pattern, owners in _rules(text):
        if _matches(pattern, path):
            found = owners
    return found


def codeowners_problems(text: str) -> list[str]:
    problems = [f"{p} has no code owner" for p in MUST_OWN if not owners_of(text, p)]
    for pattern, owners in _rules(text):
        bad = [o for o in owners if not re.match(r"^@[\w.-]+(/[\w.-]+)?$|^\S+@\S+$", o)]
        if bad:
            problems.append(f"{pattern}: {bad} are not @user, @org/team or an email")
    return problems


def test_codeowners_covers_the_risky_paths() -> None:
    text = (ROOT / ".github" / "CODEOWNERS").read_text()
    assert codeowners_problems(text) == []


def test_codeowners_names_real_paths() -> None:
    text = (ROOT / ".github" / "CODEOWNERS").read_text()
    missing = [p for p, _ in _rules(text) if "*" not in p and not (ROOT / p.lstrip("/")).exists()]
    assert not missing, f"CODEOWNERS names paths that don't exist (renamed?): {missing}"


def test_lost_owner_is_caught() -> None:
    text = "/.github/ @owner\n/.agents/ @owner\n/backend/auth.py @owner\n"
    problems = codeowners_problems(text)
    assert "supabase/migrations/20250101000000_example.sql has no code owner" in problems
    assert "mobile/lib/auth.tsx has no code owner" in problems
    # A later line with no owner un-owns the path (last match wins).
    unowned = "/.agents/ @owner\n/.agents/skills/\n"
    assert owners_of(unowned, ".agents/skills/pr-review/SKILL.md") == []
    assert codeowners_problems("/.github/ owner\n")[-1].startswith("/.github/: ['owner']")


# ---- dead code + complexity gates stay on -------------------------------------------


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def lint_gate_problems(pyproject: dict, ci: str, eslint: str) -> list[str]:
    problems = []
    lint = pyproject.get("tool", {}).get("ruff", {}).get("lint", {})
    missing = sorted({"C90", "ASYNC", "SIM", "RET", "PT"} - set(lint.get("select", [])))
    if missing:
        problems.append(f"ruff no longer selects {missing}")
    if lint.get("mccabe", {}).get("max-complexity", 99) > 10:
        problems.append("ruff max-complexity raised above 10")
    vulture = pyproject.get("tool", {}).get("vulture", {})
    if vulture.get("min_confidence", 100) > 80 or "backend" not in vulture.get("paths", []):
        problems.append("vulture must scan backend at min_confidence <= 80")
    for step in ("python3 scripts/check_generated.py", "run: vulture"):
        if step not in ci:
            problems.append(f"ci.yml no longer runs `{step}`")
    for rule in ("complexity:", '"max-depth"', '"max-nested-callbacks"', '"max-params"'):
        if rule not in eslint:
            problems.append(f"eslint.config.js lost the {rule.strip(':')} rule")
    return problems


def test_lint_gates_are_on() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    eslint = (ROOT / "mobile" / "eslint.config.js").read_text()
    assert lint_gate_problems(_pyproject(), ci, eslint) == []


def test_knip_runs_in_the_gates() -> None:
    assert (ROOT / "mobile" / "knip.jsonc").is_file(), "mobile/knip.jsonc is gone"
    pkg = ROOT / "mobile" / "package.json"
    if not pkg.exists():
        pytest.skip("mobile/package.json is created by the scaffold phase")
    gates = json.loads(pkg.read_text()).get("scripts", {}).get("gates", "")
    assert re.search(r"(^|&& )knip( |$)", gates), "npm run gates no longer runs knip"


def test_weakened_gates_are_caught() -> None:
    pyproject = {
        "tool": {
            "ruff": {"lint": {"select": ["F", "C90"], "mccabe": {"max-complexity": 15}}},
            "vulture": {"paths": ["backend"], "min_confidence": 90},
        }
    }
    problems = lint_gate_problems(pyproject, "run: ruff check", "rules: {}")
    assert "ruff no longer selects ['ASYNC', 'PT', 'RET', 'SIM']" in problems
    assert "ruff max-complexity raised above 10" in problems
    assert "vulture must scan backend at min_confidence <= 80" in problems
    assert "ci.yml no longer runs `run: vulture`" in problems
    assert "eslint.config.js lost the complexity rule" in problems
