"""Product judgement is asked, not decided (.agents/rules/product-judgement.md).

A skill that reaches a scope, copy, pricing, positioning, data or priority call has to
stop and ask the owner with a structured question. That instruction is easy to lose in
an edit ("tightened the skill") and nothing else would notice: the skill still runs, it
just starts deciding. So `.claude/harness/manifest.json` → `owner_asks` lists the
skills and subagent roles that reach those calls, and this test holds each one to it:
  - a listed skill has an `## Ask the owner` section that points at the rule
  - a listed role (subagents can't ask) returns `⚖️ QUESTION:` blocks
  - the rule itself still says how to ask in BOTH agents
  - AGENTS.md sends every agent to the rule
Each check has a negative control below.
"""

from __future__ import annotations

import json

import pytest
from harness_lib import AGENTS_DIR, ROOT

RULE = ".agents/rules/product-judgement.md"
MANIFEST = json.loads((ROOT / ".claude" / "harness" / "manifest.json").read_text())
ASKS = MANIFEST.get("owner_asks", {})


def skill_problems(text: str) -> list[str]:
    problems = []
    if "\n## Ask the owner" not in text:
        problems.append("no '## Ask the owner' section")
    if RULE not in text:
        problems.append(f"doesn't point at {RULE}")
    return problems


def role_problems(text: str) -> list[str]:
    problems = []
    if RULE not in text:
        problems.append(f"doesn't point at {RULE}")
    if "⚖️ QUESTION" not in text:
        problems.append("doesn't return ⚖️ QUESTION blocks to the orchestrator")
    return problems


def test_manifest_lists_owner_asks() -> None:
    assert len(ASKS.get("skills", [])) >= 5, "manifest owner_asks.skills is missing or gutted"
    assert ASKS.get("agents"), "manifest owner_asks.agents is missing"


@pytest.mark.parametrize("name", ASKS.get("skills", []))
def test_listed_skill_asks_the_owner(name: str) -> None:
    path = AGENTS_DIR / "skills" / name / "SKILL.md"
    assert path.is_file(), f"owner_asks lists skill {name!r}, which doesn't exist"
    problems = skill_problems(path.read_text(encoding="utf-8"))
    assert not problems, f"{name}: {'; '.join(problems)}"


@pytest.mark.parametrize("name", ASKS.get("agents", []))
def test_listed_role_returns_questions(name: str) -> None:
    path = AGENTS_DIR / "agents" / f"{name}.md"
    assert path.is_file(), f"owner_asks lists role {name!r}, which doesn't exist"
    problems = role_problems(path.read_text(encoding="utf-8"))
    assert not problems, f"{name}: {'; '.join(problems)}"


def test_rule_says_how_to_ask_in_both_agents() -> None:
    text = (ROOT / RULE).read_text(encoding="utf-8")
    for needle in ("AskUserQuestion", "request_user_input", "(Recommended)", "⚖️ QUESTION"):
        assert needle in text, f"{RULE} no longer mentions {needle}"


def test_agents_md_points_at_the_rule() -> None:
    assert RULE in (ROOT / "AGENTS.md").read_text(encoding="utf-8")


# Negative controls: the checks above can fail.
def test_skill_without_ask_section_fails() -> None:
    assert skill_problems("# Ship\n\nDo the release.\n") == [
        "no '## Ask the owner' section",
        f"doesn't point at {RULE}",
    ]
    assert skill_problems(f"# X\n\n## Ask the owner\n\nFollow `{RULE}`.\n") == []


def test_role_that_decides_alone_fails() -> None:
    assert role_problems("You decide the roadmap.") != []
    assert role_problems(f"Return ⚖️ QUESTION blocks per `{RULE}`.") == []
