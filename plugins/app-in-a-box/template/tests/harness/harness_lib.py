"""Shared helpers for the harness lint (tests/harness/).

The harness is the set of NON-code artifacts that steer every agent in this repo:
skills, agent roles, path rules, memory, hooks, AGENTS.md, workflows and JSON/TOML
configs. None of them has a compiler. A broken one does not error; it silently
changes what an agent does. These tests are the compiler.

Every rule is a pure function over text or parsed data, so each test file can prove
its rule FAILS on a planted violation (a negative control) as well as passing on the
real repo. A guard that cannot fail reads as a guard that passes.

Standard library + PyYAML only (both CI and scripts/dev-venv.sh install PyYAML).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / ".agents"
SKILLS = sorted((AGENTS_DIR / "skills").glob("*/SKILL.md"))
AGENT_ROLES = sorted((AGENTS_DIR / "agents").glob("*.md"))
RULES = sorted(p for p in (AGENTS_DIR / "rules").rglob("*.md") if p.name != "README.md")
MEMORY = AGENTS_DIR / "memory"
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
SETTINGS = ROOT / ".claude" / "settings.json"
MANIFEST = ROOT / ".claude" / "harness" / "manifest.json"
HOOKS_DIR = ROOT / ".claude" / "hooks"

_FM = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)


class FrontmatterError(ValueError):
    pass


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """(frontmatter, body). Strict YAML, the way Codex and the Agent Skills spec parse
    it: an unquoted `description: use when x: y` is a YAML error, not a long string.
    """
    m = _FM.match(text)
    if not m:
        raise FrontmatterError("no `---` frontmatter block at the top of the file")
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    return meta, m.group(2)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()
