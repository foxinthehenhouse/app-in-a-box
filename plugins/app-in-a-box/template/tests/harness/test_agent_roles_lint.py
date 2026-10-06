"""Subagent role lint (.agents/agents/*.md) and its Codex adapter (.codex/agents/*.toml).

A role is loaded by Claude Code through the .claude/agents symlink and by Codex through
a TOML file the renderer generates. Three silent failures, each negative-controlled:
  - frontmatter a strict YAML parser rejects, or no `name`/`description`: Claude Code
    skips the role, and the pr-review loop spawns a reviewer that does not exist
  - `tools:` naming a tool that does not exist: the role runs without it, quietly
  - the .md edited without regenerating the TOML: Codex runs yesterday's instructions
  - a frontmatter key Claude Code does not know (`modle:`), or a `model`/`effort` value it
    does not accept: ignored without a word, and the role runs on the default model
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from harness_lib import AGENT_ROLES, ROOT, FrontmatterError, split_frontmatter

KNOWN_TOOLS = {
    "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "Bash", "WebFetch", "WebSearch",
    "NotebookEdit", "Task", "Agent", "TodoWrite", "Skill", "LSP", "BashOutput", "KillShell",
}  # fmt: skip
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CODEX_AGENTS = ROOT / ".codex" / "agents"
# Every key a role may carry. Claude Code reads the first six; `codex_model` is the
# renderer's pin for the Codex TOML. Anything else is a typo it would swallow.
ALLOWED_KEYS = {
    "name",
    "description",
    "tools",
    "model",
    "effort",
    "codex_model",
    "disable-model-invocation",
}
EFFORTS = {"low", "medium", "high", "max"}
MODELS = {"fable", "opus", "sonnet", "haiku"}


def _identity_problems(meta: dict, stem: str) -> list[str]:
    problems: list[str] = []
    name = meta.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        problems.append("`name` missing or not lowercase-hyphenated")
    elif name != stem:
        problems.append(f"`name: {name}` does not match the file name `{stem}.md`")
    desc = meta.get("description")
    if not isinstance(desc, str) or not desc.strip():
        problems.append("`description` missing (nothing tells an orchestrator when to use it)")
    elif len(desc) > 1024:
        problems.append(f"description is {len(desc)} chars (> 1024)")
    return problems


def _routing_problems(meta: dict) -> list[str]:
    problems: list[str] = []
    model = meta.get("model")
    if model is not None and not (isinstance(model, str) and model.strip()):
        problems.append("`model:` is present but empty")
    elif isinstance(model, str) and model not in MODELS and not model.startswith("claude-"):
        problems.append(f"`model: {model}` is not one of {sorted(MODELS)} or a `claude-...` id")
    effort = meta.get("effort")
    if effort is not None and effort not in EFFORTS:
        problems.append(f"`effort: {effort}` is not one of {sorted(EFFORTS)}")
    codex_model = meta.get("codex_model")
    if codex_model is not None and not (isinstance(codex_model, str) and codex_model.strip()):
        problems.append("`codex_model:` is present but empty")
    return problems


def lint_role(text: str, stem: str) -> list[str]:
    try:
        meta, body = split_frontmatter(text)
    except FrontmatterError as exc:
        return [str(exc)]
    problems: list[str] = []
    unknown = sorted(str(k) for k in meta if k not in ALLOWED_KEYS)
    if unknown:
        problems.append(f"unknown frontmatter key(s) {unknown}: Claude Code ignores them silently")
    problems += _identity_problems(meta, stem)
    tools = meta.get("tools")
    if tools is not None:
        names = [t.strip() for t in str(tools).split(",") if t.strip()]
        unknown = [t for t in names if t not in KNOWN_TOOLS and not t.startswith("mcp__")]
        if unknown:
            problems.append(f"`tools:` names unknown tools {unknown}")
    problems += _routing_problems(meta)
    if not body.strip():
        problems.append("no instructions body (Codex gets empty developer_instructions)")
    return problems


def codex_drift(md_text: str, toml_text: str) -> list[str]:
    """Differences between a role and its generated Codex TOML."""
    meta, body = split_frontmatter(md_text)
    try:
        data = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        return [f"TOML does not parse: {exc}"]
    problems = []
    if data.get("name") != meta.get("name"):
        problems.append(f"name {data.get('name')!r} != {meta.get('name')!r}")
    if str(data.get("description", "")).strip("\"'") != str(meta.get("description", "")):
        problems.append("description differs")
    if str(data.get("developer_instructions", "")).strip() != body.strip():
        problems.append("developer_instructions differ from the .md body")
    return problems


def test_there_are_roles_to_lint() -> None:
    assert len(AGENT_ROLES) >= 3, f"only {len(AGENT_ROLES)} roles under .agents/agents/"


@pytest.mark.parametrize("role", AGENT_ROLES, ids=lambda p: p.stem)
def test_role_frontmatter_is_valid(role: Path) -> None:
    problems = lint_role(role.read_text(encoding="utf-8"), role.stem)
    assert not problems, f"{role.name}: " + "; ".join(problems)


@pytest.mark.parametrize("role", AGENT_ROLES, ids=lambda p: p.stem)
def test_codex_adapter_is_current(role: Path) -> None:
    toml = CODEX_AGENTS / f"{role.stem}.toml"
    assert toml.exists(), (
        f".codex/agents/{role.stem}.toml is missing. Regenerate the Codex adapters: "
        "render.py --adapters-only --target ."
    )
    drift = codex_drift(role.read_text(encoding="utf-8"), toml.read_text(encoding="utf-8"))
    assert not drift, f"{toml.name} is stale ({'; '.join(drift)}). Re-run --adapters-only."


def test_no_orphan_codex_roles() -> None:
    sources = {p.stem for p in AGENT_ROLES}
    orphans = sorted(p.name for p in CODEX_AGENTS.glob("*.toml") if p.stem not in sources)
    assert not orphans, f"Codex roles with no .agents/agents source (deleted role?): {orphans}"


# ---- negative controls --------------------------------------------------------

GOOD = "---\nname: rev\ndescription: Reviews things.\ntools: Read, Grep\n---\nDo the review.\n"
FULL = GOOD.replace(
    "tools: Read, Grep\n", "tools: Read, Grep\nmodel: sonnet\neffort: high\ncodex_model: gpt-5\n"
)


def test_good_role_passes() -> None:
    assert lint_role(GOOD, "rev") == []
    assert lint_role(FULL, "rev") == []
    assert lint_role(FULL.replace("model: sonnet", "model: claude-opus-4-1"), "rev") == []


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        (GOOD.replace("description: Reviews things.\n", ""), "`description` missing"),
        (GOOD.replace("name: rev", "name: other"), "does not match the file name"),
        (GOOD.replace("Read, Grep", "Read, Teleport"), "unknown tools"),
        (GOOD.replace("Do the review.\n", ""), "no instructions body"),
        (GOOD.replace("Reviews things.", "Reviews: things"), "not valid YAML"),
        (GOOD.replace("tools: Read, Grep", "model: ''"), "`model:` is present but empty"),
        (GOOD.replace("tools: Read, Grep", "modle: sonnet"), "unknown frontmatter key"),
        (GOOD.replace("tools: Read, Grep", "model: gpt-5"), "`model: gpt-5` is not one of"),
        (GOOD.replace("tools: Read, Grep", "effort: ultra"), "`effort: ultra` is not one of"),
        (GOOD.replace("tools: Read, Grep", "codex_model: ''"), "`codex_model:` is present but empty"),
    ],
    ids=[
        "no-description", "name-mismatch", "unknown-tool", "empty-body", "yaml", "empty-model",
        "unknown-key", "bad-model", "bad-effort", "empty-codex-model",
    ],  # fmt: skip
)
def test_each_rule_can_fail(text: str, needle: str) -> None:
    assert any(needle in p for p in lint_role(text, "rev")), lint_role(text, "rev")


def test_codex_drift_can_fail() -> None:
    fresh = (
        'name = "rev"\ndescription = "Reviews things."\ndeveloper_instructions = "Do the review."\n'
    )
    assert codex_drift(GOOD, fresh) == []
    stale = fresh.replace("Do the review.", "Old instructions.")
    assert codex_drift(GOOD, stale) == ["developer_instructions differ from the .md body"]
    assert codex_drift(GOOD, "name = ")[0].startswith("TOML does not parse")
