"""SessionStart orientation (.claude/hooks/session-start.sh) puts the facts in context.

An instruction ("read the memory index at session start") is honoured when remembered. A
mechanism puts the index body in the very first message, so nothing has to be remembered.
The hook also warns when the branch carries no ticket id, which is the one thing the
`ticket` CI check cannot catch until the PR exists. Each line is driven against a
throwaway repo and each warning has a case that must NOT fire.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from harness_lib import HOOKS_DIR

HOOK = HOOKS_DIR / "session-start.sh"
MAIN = "ma" + "in"
DISTINCT = "never router.replace a bare route group"


def _git(cwd: Path, *args: str) -> None:
    base = [
        "git",
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "-c",
        "commit.gpgsign=false",
    ]
    assert subprocess.run([*base, *args], cwd=cwd, capture_output=True, text=True).returncode == 0


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / ".agents" / "memory").mkdir(parents=True)
    (r / ".agents" / "memory" / "MEMORY.md").write_text(
        f"# Memory index\n\n- [Auth loop](auth_loop.md): {DISTINCT}\n"
    )
    _git(r, "init", "-q", "-b", MAIN)
    _git(r, "config", "core.hooksPath", ".githooks")
    (r / "README.md").write_text("x\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "init")
    return r


def run_hook(repo: Path) -> str:
    out = subprocess.run(
        ["bash", str(HOOK)],
        input="{}",
        cwd=repo,
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(repo)},
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_memory_index_body_is_in_the_first_message(repo: Path) -> None:
    out = run_hook(repo)
    assert "Memory: 1 note(s)" in out
    assert DISTINCT in out, "only a count was printed; the index itself must be in context"


def test_memory_body_is_bounded(repo: Path) -> None:
    """A runaway index (reflect not run for months) must not flood the session."""
    lines = [f"- [N{i}](n{i}.md): line number {i}" for i in range(400)]
    (repo / ".agents" / "memory" / "MEMORY.md").write_text("\n".join(lines) + "\n")
    out = run_hook(repo)
    assert "line number 10" in out
    assert "line number 300" not in out
    assert out.count("\n") < 120


def test_no_memory_file_is_fine(repo: Path) -> None:
    (repo / ".agents" / "memory" / "MEMORY.md").unlink()
    out = run_hook(repo)
    assert "## Session start" in out and "Memory:" not in out


@pytest.mark.parametrize("branch", ["feat/login", "fix-redirect", "alex/polish"])
def test_branch_without_a_ticket_id_warns(repo: Path, branch: str) -> None:
    _git(repo, "switch", "-qc", branch)
    assert "no ticket id" in run_hook(repo)


@pytest.mark.parametrize(
    "branch", ["feat/42-login", "fix/#7-redirect", "feat/APP-12-login", "alex/app-552-x"]
)
def test_branch_with_a_ticket_id_does_not_warn(repo: Path, branch: str) -> None:
    _git(repo, "switch", "-qc", branch)
    assert "no ticket id" not in run_hook(repo)


def test_main_gets_the_branch_hint_not_the_ticket_warning(repo: Path) -> None:
    out = run_hook(repo)
    assert "create a branch before editing" in out and "no ticket id" not in out


def test_git_hooks_off_is_called_out(repo: Path) -> None:
    assert "git hooks are off" not in run_hook(repo)
    _git(repo, "config", "--unset", "core.hooksPath")
    assert "git hooks are off" in run_hook(repo)


def test_hook_fails_open_outside_a_project(tmp_path: Path) -> None:
    out = subprocess.run(
        ["bash", str(HOOK)], input="{}", cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path / "missing")}, timeout=30,
    )  # fmt: skip
    assert out.returncode == 0
