"""The always-loaded context must fit, and must still describe reality.

AGENTS.md (+ the nested mobile/ and backend/ ones) is read by every agent at the start
of every session: Codex natively, Claude Code through `@AGENTS.md` in CLAUDE.md. Several
things WRITE these files (reflect, harness-optimize, build-feature, you) and nothing
else checks what they claim. Failures are quiet:

  - **Size.** Codex stops reading project docs at 32 KiB (`project_doc_max_bytes`),
    counting the root file plus every nested AGENTS.md on the way to the working
    directory. Past that, the rules at the bottom simply aren't there. Hard fail.
  - **Length budget.** Every line costs context in every session. Over the manifest's
    `agents_md_lines` WARNS (the budget is an accretion alarm, not a merge gate).
  - **Dead references.** A path that moved or a skill that was retired keeps being
    asserted with the same confidence. Every backticked path and every named skill
    must resolve.
  - **Claude import.** A directory with an AGENTS.md needs a CLAUDE.md that imports
    it, or Claude Code never sees it.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest
from harness_lib import AGENTS_DIR, MANIFEST, ROOT, load_json

CODEX_MAX_BYTES = 32 * 1024
AGENTS_DOCS = sorted(
    p for p in ROOT.rglob("AGENTS.md") if "node_modules" not in p.parts and ".git" not in p.parts
)
CONTEXT_DOCS = [
    *AGENTS_DOCS,
    AGENTS_DIR / "README.md",
    *sorted((AGENTS_DIR / "rules").glob("*.md")),
]
# Written by a later App in a Box phase (interview / feature-discovery). Exempt ONLY
# while appbox.yaml is absent, i.e. in a pristine render. After the interview they
# must exist like everything else.
LATER_PHASE = {
    "docs/product/BRIEF.md": "written by the interview phase",
    "docs/product/VALIDATION.md": "written by the idea check (phase 1a)",
    "docs/product/": "created with BRIEF.md by the interview phase",
    "appbox.yaml": "the setup record, written by the interview phase",
}
# Conventions named before their folder exists. Keep this tiny and justified.
CONVENTIONS = {
    "services/": "backend/AGENTS.md names where the first feature's pure logic goes",
    "mobile/.env": "local dev env file: gitignored, created from mobile/.env.example",
    "expo-router/unstable-native-tabs": "an import specifier (a module), not a repo path",
}
PATH_EXT = r"\.(md|py|ts|tsx|js|json|toml|sh|sql|ya?ml|txt)"
# "`backlog` skill", "skill `backlog`", or Codex's "`$backlog`". A bare `/x` is not
# counted: in these docs it is usually an API route (`/health`), not a skill.
SKILL_REF = re.compile(
    r"`([a-z][a-z0-9-]+)`\s+skill\b|\bskill\s+`([a-z][a-z0-9-]+)`|`\$([a-z][a-z0-9-]+)`"
)
GENERIC_SKILL_WORDS = {"name"}  # "`/name` in Claude Code and `$name` in Codex"


def path_refs(text: str) -> set[str]:
    """Backticked tokens that claim to be a repo path (not globs, templates or code)."""
    refs = set()
    for tok in re.findall(r"`([^`\n]+)`", text):
        tok = tok.strip()
        if " " in tok or tok.startswith(("/", "$", "@", "http")) or tok in {".", ".."}:
            continue
        if any(c in tok for c in "*<>{}") or "YYYY" in tok or "..." in tok:
            continue
        if "/" in tok or re.search(PATH_EXT + "$", tok):
            refs.add(tok)
    return refs


def skill_refs(text: str) -> set[str]:
    found = set()
    for m in SKILL_REF.finditer(text):
        name = next(g for g in m.groups() if g)
        if name not in GENERIC_SKILL_WORDS:
            found.add(name)
    return found


def dead_paths(doc: Path, root: Path, exempt: set[str]) -> list[str]:
    """Refs that resolve nowhere. A ref may be relative to the repo root, to the doc's
    own folder, or to a package folder with its own AGENTS.md (a rule's `app/(app)/`
    means `mobile/app/(app)/`)."""
    bases = [root, doc.parent] + [p.parent for p in root.glob("*/AGENTS.md")]
    names = {p.name for p in root.rglob("*") if "node_modules" not in p.parts}
    dead = []
    for ref in sorted(path_refs(doc.read_text(encoding="utf-8"))):
        clean = ref.rstrip("/")
        if ref in exempt or any((b / clean).exists() for b in bases):
            continue
        if "/" not in clean and clean in names:  # a bare file name, e.g. `theme.ts`
            continue
        dead.append(ref)
    return dead


def _exempt() -> set[str]:
    later = set() if (ROOT / "appbox.yaml").exists() else set(LATER_PHASE)
    return later | set(CONVENTIONS)


def test_there_are_docs_to_check() -> None:
    assert (ROOT / "AGENTS.md").exists()
    assert len(AGENTS_DOCS) >= 2


def chain_overflow(root: Path, doc: Path) -> int:
    """Bytes over Codex's limit for the root AGENTS.md + `doc` (0 when it fits)."""
    size = sum(p.stat().st_size for p in {root / "AGENTS.md", doc})
    return max(0, size - CODEX_MAX_BYTES)


def lines_over(text: str, limit: int | None) -> int:
    n = len(text.splitlines())
    return max(0, n - limit) if limit else 0


@pytest.mark.parametrize("doc", AGENTS_DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_codex_reads_the_whole_chain(doc: Path) -> None:
    """Root + this nested file is what Codex concatenates for work in that folder."""
    over = chain_overflow(ROOT, doc)
    assert not over, (
        f"AGENTS.md chain for {doc.relative_to(ROOT)} is {over} bytes over Codex's "
        f"{CODEX_MAX_BYTES}-byte limit. Move detail into .agents/rules/ or a skill."
    )


def test_agents_md_line_budget_warns_not_fails() -> None:
    limit = load_json(MANIFEST).get("complexity_budget", {}).get("limits", {})
    limit = limit.get("agents_md_lines")
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    n = len(text.splitlines())
    if lines_over(text, limit):
        warnings.warn(
            f"AGENTS.md is {n} lines against a budget of {limit}; harness-optimize owes a "
            "pruning look (manifest.complexity_budget).",
            UserWarning,
            stacklevel=1,
        )
    assert n > 0


@pytest.mark.parametrize("doc", AGENTS_DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_claude_md_imports_agents_md(doc: Path) -> None:
    claude = doc.with_name("CLAUDE.md")
    why = (
        f"{claude.relative_to(ROOT)} must exist and contain `@AGENTS.md`, or Claude Code "
        "never reads this AGENTS.md"
    )
    assert claude.exists(), why
    assert "@AGENTS.md" in claude.read_text(encoding="utf-8"), why


@pytest.mark.parametrize("doc", CONTEXT_DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_path_reference_exists(doc: Path) -> None:
    dead = dead_paths(doc, ROOT, _exempt())
    assert not dead, f"{doc.relative_to(ROOT)} references paths that do not exist: {dead}"


@pytest.mark.parametrize("doc", CONTEXT_DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_named_skill_exists(doc: Path) -> None:
    known = {p.parent.name for p in (AGENTS_DIR / "skills").glob("*/SKILL.md")}
    unknown = sorted(skill_refs(doc.read_text(encoding="utf-8")) - known)
    assert not unknown, f"{doc.relative_to(ROOT)} names skills that do not exist: {unknown}"


def test_agents_md_names_the_core_skills() -> None:
    """Vacuity check: the extractor must actually find the skills AGENTS.md names."""
    assert {"backlog", "pr-review", "reflect"} <= skill_refs(
        (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    )


# ---- negative controls --------------------------------------------------------


def test_dead_path_is_caught(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "file.py").write_text("")
    doc = tmp_path / "AGENTS.md"
    doc.write_text("See `real/file.py`, `gone/away.py`, `real/**` and `<kit>/x.py`.\n")
    assert dead_paths(doc, tmp_path, set()) == ["gone/away.py"]
    assert dead_paths(doc, tmp_path, {"gone/away.py"}) == []


def test_retired_skill_is_caught() -> None:
    text = "Use the `ghost` skill, then `$pr-review`, then call `/health`."
    assert skill_refs(text) == {"ghost", "pr-review"}


def test_size_rule_can_fail(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("x" * 30_000)
    nested = tmp_path / "mobile" / "AGENTS.md"
    nested.parent.mkdir()
    nested.write_text("y" * 3_000)
    assert chain_overflow(tmp_path, nested) == 33_000 - CODEX_MAX_BYTES
    nested.write_text("y" * 100)
    assert chain_overflow(tmp_path, nested) == 0


def test_line_budget_can_fire() -> None:
    assert lines_over("a\n" * 161, 160) == 1
    assert lines_over("a\n" * 160, 160) == 0
