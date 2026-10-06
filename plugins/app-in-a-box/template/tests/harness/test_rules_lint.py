"""Path-scoped rules (.agents/rules/*.md) and the hook that injects them.

A rule reaches an agent two ways: Claude Code's `inject-path-rules.py` hook injects it
on the first edit of a matching file, and Codex reads it because AGENTS.md's path-rule
table names it. Either link can break silently:
  - no `globs:` (or an empty body): the hook skips the rule without a word
  - a rule missing from AGENTS.md's table, or a glob missing from its row: Codex never
    learns the rule exists, or never learns it applies to that path
  - a glob that matches nothing the rule is about: it never fires
Rules are parsed with the hook's OWN parser, so this test and the hook can't disagree
about what a valid rule is. Each check has a negative control.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from harness_lib import AGENTS_DIR, HOOKS_DIR, ROOT

HOOK = HOOKS_DIR / "inject-path-rules.py"
TOP_RULES = sorted(p for p in (AGENTS_DIR / "rules").glob("*.md") if p.name != "README.md")
ALL_RULES = sorted(p for p in (AGENTS_DIR / "rules").rglob("*.md") if p.name != "README.md")


def _load_hook():
    spec = importlib.util.spec_from_file_location("inject_path_rules", HOOK)
    assert spec
    assert spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()


def lint_rule(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    parsed = hook.parse_rule(str(path))
    if parsed is None:
        return ["the hook cannot parse it (needs `---` frontmatter, `globs:` and a body)"]
    problems = []
    if not parsed["globs"]:
        problems.append("`globs:` has no include patterns")
    if not re.search(r"^description:\s*\S", text.split("---")[1], re.M):
        problems.append("`description:` missing")
    if parsed.get("match") and not parsed["match"].search(parsed.get("example") or ""):
        problems.append("`match:` rule needs an `example:` line that its regex matches")
    return problems


def rows_naming(agents_md: str, rule_name: str) -> list[str]:
    """AGENTS.md path-rule table rows whose 'Read first' cell names this rule."""
    return [
        ln
        for ln in agents_md.splitlines()
        if ln.startswith("|") and f".agents/rules/{rule_name}" in ln
    ]


def globs_missing_from_rows(rows: list[str], globs: list[str]) -> list[str]:
    """Globs the rule declares that no row naming it lists in its 'Editing' cell."""
    listed: set[str] = set()
    for row in rows:
        cells = row.strip().strip("|").split("|")
        listed |= set(re.findall(r"`([^`]+)`", cells[0]))
    return [g for g in globs if g not in listed]


def example_path(glob: str) -> str:
    """A concrete path a glob must match (`backend/**` -> `backend/x/y.py`)."""
    p = glob.replace("**/", "x/").replace("**", "x/y.py").replace("*", "f")
    return p.replace("?", "q")


def run_hook(file_path: str, root: Path, tmp: Path, content: str = "") -> str:
    tool_input = {"file_path": file_path, **({"content": content} if content else {})}
    event = {"tool_input": tool_input, "session_id": f"t{os.getpid()}{tmp.name}"}
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "TMPDIR": str(tmp)}
    out = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_there_are_rules() -> None:
    assert len(TOP_RULES) >= 3


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda p: p.relative_to(AGENTS_DIR).as_posix())
def test_rule_is_well_formed(rule: Path) -> None:
    problems = lint_rule(rule)
    assert not problems, f"{rule.name}: " + "; ".join(problems)


@pytest.mark.parametrize("rule", TOP_RULES, ids=lambda p: p.name)
def test_rule_is_listed_for_codex(rule: Path) -> None:
    """Every glob the rule declares appears in a table row that names the rule. Codex has
    no hook: the row IS its trigger, so a glob missing from the row is a path the rule
    silently does not cover for Codex."""
    agents_md = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rows = rows_naming(agents_md, rule.name)
    assert rows, f"{rule.name} is not in AGENTS.md's path-rule table, so Codex never reads it"
    parsed = hook.parse_rule(str(rule))
    assert parsed is not None
    missing = globs_missing_from_rows(rows, parsed["globs"])
    assert not missing, (
        f"{rule.name} declares globs {missing} that its AGENTS.md row does not list; "
        "add them to the row (or drop them from the rule)"
    )


@pytest.mark.parametrize("rule", TOP_RULES, ids=lambda p: p.name)
def test_hook_injects_rule_for_each_glob(rule: Path, tmp_path: Path) -> None:
    """Drive the REAL hook with a path each glob must match (and, for a `match:` rule,
    the edit text its `example:` gives)."""
    parsed = hook.parse_rule(str(rule))
    for i, glob in enumerate(parsed["globs"]):
        sub = tmp_path / str(i)
        sub.mkdir()
        target = str(ROOT / example_path(glob))
        out = run_hook(target, ROOT, sub, parsed.get("example") or "")
        assert rule.name in out, f"{rule.name} not injected for {example_path(glob)} ({glob})"


# ---- negative controls --------------------------------------------------------


def test_hook_injects_nothing_for_an_unrelated_path(tmp_path: Path) -> None:
    assert run_hook(str(ROOT / "LICENSE-nothing.txt"), ROOT, tmp_path) == ""


def test_match_rule_stays_quiet_when_the_edit_is_not_about_it(tmp_path: Path) -> None:
    target = str(ROOT / "supabase" / "migrations" / "x.sql")
    (tmp_path / "quiet").mkdir()
    (tmp_path / "loud").mkdir()
    quiet = run_hook(target, ROOT, tmp_path / "quiet", "alter table t add column visit_count int;")
    assert "privacy-columns.md" not in quiet
    loud = run_hook(
        target, ROOT, tmp_path / "loud", "create table t (id uuid, contact_email text);"
    )
    assert "privacy-columns.md" in loud
    assert "`contact_email text`" in loud


def test_match_rule_without_a_matching_example_is_caught(tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text(
        "---\ndescription: d\nglobs: a/**\nmatch: \\bemail\\b\nexample: phone\n---\nbody\n"
    )
    assert any("example" in x for x in lint_rule(p)), lint_rule(p)


def test_hook_fires_once_per_session(tmp_path: Path) -> None:
    target = str(ROOT / "supabase" / "migrations" / "x.sql")
    assert "db-migrations.md" in run_hook(target, ROOT, tmp_path)
    assert run_hook(target, ROOT, tmp_path) == ""


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("---\ndescription: d\n---\nbody\n", "cannot parse"),
        ("---\ndescription: d\nglobs: a/**\n---\n\n", "cannot parse"),
        ("---\nglobs: a/**\n---\nbody\n", "`description:` missing"),
        ("---\ndescription: d\nglobs: !a/**\n---\nbody\n", "no include patterns"),
    ],
    ids=["no-globs", "empty-body", "no-description", "only-excludes"],
)
def test_each_rule_can_fail(text: str, needle: str, tmp_path: Path) -> None:
    p = tmp_path / "r.md"
    p.write_text(text)
    assert any(needle in x for x in lint_rule(p)), lint_rule(p)


def test_table_row_rule_can_fail() -> None:
    md = "| `a/**`, `b.ts` | `.agents/rules/r.md` |\n| `c/**` | `.agents/rules/other.md` |\n"
    rows = rows_naming(md, "r.md")
    assert len(rows) == 1
    assert globs_missing_from_rows(rows, ["a/**", "b.ts"]) == []
    assert globs_missing_from_rows(rows, ["a/**", "b.ts", "c/**"]) == ["c/**"]
    assert rows_naming(md, "missing.md") == []
    assert globs_missing_from_rows([], ["a/**"]) == ["a/**"]


def test_glob_matching_semantics() -> None:
    assert hook.glob_to_re("backend/**").match("backend/a/b.py")
    assert hook.glob_to_re("mobile/app/**").match("mobile/app/(app)/index.tsx")
    assert not hook.glob_to_re("mobile/lib/*.ts").match("mobile/lib/sub/x.ts")
    assert not hook.glob_to_re("supabase/migrations/**").match("backend/main.py")
