"""Skill frontmatter lint (.agents/skills/*/SKILL.md), for Claude Code AND Codex.

The listing (`name` + `description`) is the only part of a skill that is always in
context, so it decides when the skill fires. A broken one is invisible when you read
the file: Claude Code tolerates an unquoted colon or an over-long description, Codex
parses the frontmatter as strict YAML and drops the skill, and a description past
1,024 characters (the Agent Skills spec limit) is cut. A real app shipped exactly that:
one prepended sentence pushed a description to 1,140 chars.

Rules, each with a negative control below:
  - frontmatter is strict YAML (an unquoted `when x: y` breaks Codex)
  - name present, matches the directory, lowercase-hyphen, <= 64 chars, no reserved words
  - description present, <= 1024 chars, no XML tags, says when to use the skill
  - body present, SKILL.md <= 500 lines (move detail into references/)
  - only known frontmatter keys (a misspelled `disable-model-invocation` is silently on)
  - Claude Code's .claude/skills adapter exposes exactly the same skills
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from harness_lib import AGENTS_DIR, ROOT, SKILLS, FrontmatterError, split_frontmatter

MAX_DESCRIPTION = 1024
MAX_NAME = 64
MAX_LINES = 500
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED = ("anthropic", "claude")
TRIGGER_RE = re.compile(r"\bUse\b|\bInvoke\b|\bRun\b", re.I)
# Keys Claude Code / the Agent Skills spec read. Anything else is ignored without a word.
ALLOWED_KEYS = {
    "name", "description", "disable-model-invocation", "model", "user-invocable",
    "allowed-tools", "context", "agent", "when_to_use", "argument-hint", "paths",
}  # fmt: skip


def lint_skill(text: str, dirname: str) -> list[str]:
    try:
        meta, body = split_frontmatter(text)
    except FrontmatterError as exc:
        return [str(exc)]
    problems: list[str] = []
    unknown = sorted(str(k) for k in meta if k not in ALLOWED_KEYS)
    if unknown:
        problems.append(
            f"unknown frontmatter key(s) {unknown}: ignored silently, so a typo is a no-op"
        )
    name = meta.get("name")
    if not isinstance(name, str) or not name:
        problems.append("`name` missing")
    else:
        if name != dirname:
            problems.append(f"`name: {name}` does not match its directory `{dirname}`")
        if not NAME_RE.match(name) or len(name) > MAX_NAME:
            problems.append(f"`name: {name}` must be lowercase-hyphenated and <= {MAX_NAME} chars")
        if any(word in name for word in RESERVED):
            problems.append(f"`name: {name}` contains a reserved word ({', '.join(RESERVED)})")
    desc = meta.get("description")
    if not isinstance(desc, str) or not desc.strip():
        problems.append("`description` missing (the skill can never trigger)")
    else:
        if len(desc) > MAX_DESCRIPTION:
            problems.append(
                f"description is {len(desc)} chars (> {MAX_DESCRIPTION}); lead with the "
                "trigger and trim the rest"
            )
        if re.search(r"<[A-Za-z/][^>]*>", desc):
            problems.append("description contains an XML/HTML tag (not allowed by the spec)")
        if not TRIGGER_RE.search(desc):
            problems.append("description never says when to use it ('Use when ...')")
    if not body.strip():
        problems.append("SKILL.md has no body")
    if text.count("\n") + 1 > MAX_LINES:
        problems.append(f"SKILL.md is over {MAX_LINES} lines; move detail into references/")
    return problems


def test_there_are_skills_to_lint() -> None:
    """A lint aimed at nothing is worse than no lint."""
    assert len(SKILLS) >= 5, f"only {len(SKILLS)} skills found under .agents/skills/"


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_skill_frontmatter_is_valid(skill: Path) -> None:
    problems = lint_skill(skill.read_text(encoding="utf-8"), skill.parent.name)
    assert not problems, f"{skill.parent.name}: " + "; ".join(problems)


def test_claude_adapter_exposes_the_same_skills() -> None:
    adapter = ROOT / ".claude" / "skills"
    if not adapter.exists():
        pytest.fail(".claude/skills is missing: re-run the renderer with --adapters-only")
    via_claude = sorted(p.parent.name for p in adapter.glob("*/SKILL.md"))
    source = sorted(p.parent.name for p in (AGENTS_DIR / "skills").glob("*/SKILL.md"))
    assert via_claude == source, (
        f".claude/skills ({via_claude}) is out of sync with .agents/skills ({source}); "
        "it should be a symlink. Re-run the renderer with --adapters-only."
    )


# ---- negative controls: every rule must be able to fail ----------------------

GOOD = "---\nname: ok\ndescription: Does a thing. Use when asked to do the thing.\n---\nBody\n"


def test_good_skill_passes() -> None:
    assert lint_skill(GOOD, "ok") == []
    rich = GOOD.replace(
        "---\nBody",
        "argument-hint: <ticket>\nuser-invocable: true\nallowed-tools: Read, Grep\n"
        "context: fork\nagent: triage\nwhen_to_use: Use when asked.\npaths: backend/**\n"
        "disable-model-invocation: true\nmodel: sonnet\n---\nBody",
    )
    assert lint_skill(rich, "ok") == []


@pytest.mark.parametrize(
    "text, dirname, needle",
    [
        ("---\nname: ok\n---\nBody\n", "ok", "description` missing"),
        ("---\ndescription: Use when x.\n---\nBody\n", "ok", "`name` missing"),
        (GOOD, "other", "does not match its directory"),
        (GOOD.replace("name: ok", "name: Bad_Name"), "Bad_Name", "lowercase-hyphenated"),
        (GOOD.replace("name: ok", "name: claude-helper"), "claude-helper", "reserved word"),
        (
            "---\nname: ok\ndescription: Use when " + "x" * MAX_DESCRIPTION + "\n---\nB\n",
            "ok",
            "chars (>",
        ),
        ("---\nname: ok\ndescription: Use when <b>bold</b>.\n---\nB\n", "ok", "XML/HTML tag"),
        ("---\nname: ok\ndescription: Does a thing.\n---\nB\n", "ok", "when to use"),
        ("---\nname: ok\ndescription: Use when a: b\n---\nB\n", "ok", "not valid YAML"),
        ("no frontmatter at all\n", "ok", "no `---` frontmatter"),
        (GOOD.replace("Body\n", ""), "ok", "no body"),
        (GOOD + "line\n" * MAX_LINES, "ok", "over 500 lines"),
        (
            GOOD.replace("---\nBody", "disable_model_invocation: true\n---\nBody"),
            "ok",
            "unknown frontmatter key",
        ),
    ],
    ids=[
        "no-description",
        "no-name",
        "name-dir-mismatch",
        "name-charset",
        "reserved-word",
        "too-long",
        "xml-tag",
        "no-trigger",
        "codex-yaml-colon",
        "no-frontmatter",
        "empty-body",
        "too-many-lines",
        "unknown-key",
    ],
)
def test_each_rule_can_fail(text: str, dirname: str, needle: str) -> None:
    problems = lint_skill(text, dirname)
    assert any(needle in p for p in problems), f"rule did not fire for {needle!r}: {problems}"
