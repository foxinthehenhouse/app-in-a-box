"""The git-tracked memory vault (.agents/memory/) and the harness's portability.

Memory is shared by every agent and machine through git, and the recall hook injects
note text into prompts, so three things must hold (each negative-controlled):

1. The index matches disk both ways. `MEMORY.md` is the only file read in full every
   session; a note missing from it is on disk and functionally invisible, and an
   index line pointing at nothing is a lie told every session. <= 45 entries.
2. Nothing secret-shaped is committed (a committed key would leak twice: in git and
   in every prompt that recalls the note).
3. No absolute machine path (`/Users/alex/...`, `/home/...`, `C:\\...`) in the vault,
   the rules, skills, roles or hooks. It works on the laptop that wrote it and
   nowhere else: not in CI, not in a cloud agent, not in a teammate's clone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from harness_lib import AGENTS_DIR, HOOKS_DIR, MEMORY, ROOT

MAX_ENTRIES = 45
SECRET_PATTERNS = [
    r"(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_-]{20,}",
    r"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9]{32,}",
    r"gh[pousr]_[A-Za-z0-9]{30,}",
    r"github_pat_[A-Za-z0-9_]{30,}",
    r"AKIA[0-9A-Z]{16}",
    r"BEGIN [A-Z ]*PRIVATE KEY",
    r"eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}",
    r"postgres(ql)?://[^\s:/]+:[^\s@]+@",
    r"xox[abprs]-[A-Za-z0-9-]{10,}",
    r"sb_secret_[A-Za-z0-9_-]{16,}",
    r"phx_[A-Za-z0-9]{20,}",
    r"(?i)bearer\s+[A-Za-z0-9._-]{30,}",
]
MACHINE_PATH = re.compile(
    r"(?<![\w.])(/Users/[A-Za-z0-9._-]+|/home/[a-z][a-z0-9._-]*/|[A-Z]:\\\\?Users)"
)
PORTABLE_SCAN = [
    MEMORY,
    AGENTS_DIR / "rules",
    AGENTS_DIR / "skills",
    AGENTS_DIR / "agents",
    HOOKS_DIR,
]


def notes(vault: Path) -> list[Path]:
    return [p for p in vault.glob("*.md") if p.name != "MEMORY.md" and not p.name.startswith("_")]


def index_problems(vault: Path) -> list[str]:
    """Same measurement as harness-healthcheck check 4 (code spans are examples)."""
    index_md = vault / "MEMORY.md"
    if not index_md.exists():
        return ["MEMORY.md missing"]
    index = re.sub(r"`[^`]*`", "", index_md.read_text(encoding="utf-8"))
    linked = {Path(x).name for x in re.findall(r"\]\(([^)]+\.md)\)", index)}
    on_disk = {p.name for p in notes(vault)}
    problems = []
    if on_disk - linked:
        problems.append(
            f"notes on disk but not in MEMORY.md (invisible): {sorted(on_disk - linked)}"
        )
    if linked - on_disk:
        problems.append(f"MEMORY.md links to notes that do not exist: {sorted(linked - on_disk)}")
    entries = len(re.findall(r"^\s*-\s*\[", index, re.M))
    if entries > MAX_ENTRIES:
        problems.append(f"MEMORY.md has {entries} entries (> {MAX_ENTRIES}); run the reflect skill")
    return problems


def secret_hits(text: str) -> list[str]:
    return [pat for pat in SECRET_PATTERNS if re.search(pat, text)]


def machine_paths(text: str) -> list[str]:
    return MACHINE_PATH.findall(text)


def _files(dirs: list[Path]) -> list[Path]:
    out = []
    for d in dirs:
        if d.is_dir():
            out += [p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return sorted(out)


def test_memory_index_matches_disk() -> None:
    problems = index_problems(MEMORY)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("path", _files([MEMORY]), ids=lambda p: p.name)
def test_no_secret_shaped_content_in_memory(path: Path) -> None:
    hits = secret_hits(path.read_text(encoding="utf-8", errors="replace"))
    assert not hits, f"{path.relative_to(ROOT)} contains secret-shaped text: {hits}"


def test_harness_has_no_machine_local_paths() -> None:
    offenders = []
    for p in _files(PORTABLE_SCAN):
        found = machine_paths(p.read_text(encoding="utf-8", errors="replace"))
        if found:
            offenders.append(f"{p.relative_to(ROOT)}: {sorted(set(found))}")
    assert not offenders, (
        "absolute machine paths in the harness (use $CLAUDE_PROJECT_DIR, `git rev-parse "
        "--show-toplevel`, ~ or a repo-relative path):\n" + "\n".join(offenders)
    )


def test_the_scan_sees_files() -> None:
    """Vacuity: a scan whose globs stopped matching reports 'clean'."""
    assert len(_files(PORTABLE_SCAN)) >= 20


# ---- negative controls --------------------------------------------------------


def test_index_drift_is_caught(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("- [A](a.md): x\n- [Ghost](ghost.md): y\n")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "hidden.md").write_text("h")
    problems = index_problems(tmp_path)
    assert any("hidden.md" in p for p in problems)
    assert any("ghost.md" in p for p in problems)
    (tmp_path / "MEMORY.md").write_text("- [A](a.md): x\n- [H](hidden.md): y\n")
    assert index_problems(tmp_path) == []
    many = "".join(f"- [N{i}](a.md): x\n" for i in range(MAX_ENTRIES + 1))
    (tmp_path / "MEMORY.md").write_text(many + "- [H](hidden.md): y\n")
    assert any("entries" in p for p in index_problems(tmp_path))


def test_every_secret_pattern_can_fire() -> None:
    """Samples are built here, not derived from the patterns, so a broken regex fails."""
    samples = [
        "sk-ant-" + "a" * 24, "sk-" + "b" * 40, "ghp_" + "c" * 36, "github_pat_" + "d" * 40,
        "AKIA" + "D" * 16, "-----BEGIN RSA PRIVATE KEY-----", "eyJ" + "e" * 32 + "." + "f" * 32,
        "postgresql://u:pw@host/db", "xoxb-" + "1" * 12, "sb_secret_" + "g" * 20,
        "phx_" + "h" * 24, "Bearer " + "i" * 40,
    ]  # fmt: skip
    for pat in SECRET_PATTERNS:
        assert any(re.search(pat, s) for s in samples), f"/{pat}/ matches none of its samples"
    assert not secret_hits("ask-for-help-when-deciding and postgresql://localhost/db")


def test_machine_path_rule_can_fail() -> None:
    assert machine_paths("see /Users/alex/code/app/x.py")
    assert machine_paths("cd /home/kyle/app")
    assert not machine_paths("~/.claude/projects and $HOME/.cache and /tmp/x and ./home/x")
