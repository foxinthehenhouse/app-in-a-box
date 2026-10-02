"""The healthcheck sees memory that never left this machine.

Claude Code keeps its own auto-memory under `<claude_projects_dir>/<slug>/memory/`, keyed
by the checkout path exactly like transcripts. Those notes exist on one laptop: CI, Codex
and every teammate read `.agents/memory/` instead. `harness-healthcheck.py` compares the
two by filename and nudges "copy it into .agents/memory via a PR". It derives the local
dir through harness_paths (one slug rule), fails open when the dir is absent, and is
driven here through the REAL hook with the projects dir redirected by env.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from harness_lib import HOOKS_DIR

HEALTHCHECK = HOOKS_DIR / "harness-healthcheck.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


paths = _load("harness_paths", HOOKS_DIR / "harness_paths.py")
sys.path.insert(0, str(HOOKS_DIR))
hc = _load("harness_healthcheck", HEALTHCHECK)


def _project(tmp_path: Path) -> tuple[Path, Path]:
    """A throwaway project with a repo vault, plus a fake Claude projects dir whose
    per-checkout memory dir is derived the way the hook derives it."""
    root = tmp_path / "proj"
    vault = root / ".agents" / "memory"
    vault.mkdir(parents=True)
    (vault / "MEMORY.md").write_text("# Memory index\n\n- [Shared](shared.md): x\n")
    (vault / "shared.md").write_text("shared")
    projects = tmp_path / "projects"
    local = projects / paths.slug(paths.canonical_root(str(root))) / "memory"
    local.mkdir(parents=True)
    (local / "MEMORY.md").write_text("- [Shared](shared.md)\n- [Local](local_only.md)\n")
    (local / "shared.md").write_text("shared")
    (local / "_scratch.md").write_text("scratch")
    return root, local


def run_session(root: Path, tmp_path: Path) -> str:
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(root),
        "APPBOX_CLAUDE_PROJECTS_DIR": str(tmp_path / "projects"),
        "APPBOX_STATE_DIR": str(tmp_path / "state"),
    }
    out = subprocess.run(
        [sys.executable, str(HEALTHCHECK), "--session"],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        cwd=root,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_local_only_note_is_nudged_by_the_real_hook(tmp_path: Path) -> None:
    root, local = _project(tmp_path)
    (local / "local_only.md").write_text("only here")
    out = run_session(root, tmp_path)
    assert "machine-local memory note" in out and "local_only.md" in out
    assert "shared.md" not in out, "a note already in the vault was reported"
    assert ".agents/memory" in out and "PR" in out


def test_nothing_to_port_means_no_nudge(tmp_path: Path) -> None:
    root, _ = _project(tmp_path)
    assert "machine-local" not in run_session(root, tmp_path)


def test_absent_local_dir_fails_open(tmp_path: Path) -> None:
    root, local = _project(tmp_path)
    for p in local.iterdir():
        p.unlink()
    local.rmdir()
    out = run_session(root, tmp_path)
    assert "machine-local" not in out


def test_pure_rule_can_fail(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (repo, a, b):
        d.mkdir()
    (repo / "x.md").write_text("")
    (a / "x.md").write_text("")
    (a / "MEMORY.md").write_text("")
    (a / "_journal.md").write_text("")
    (b / "y.md").write_text("")
    assert hc.unported_local_memory([a], repo) == []
    assert hc.unported_local_memory([a, b], repo) == ["y.md"]
    assert hc.unported_local_memory([tmp_path / "nope"], repo) == []
    assert hc.unported_local_memory([b], tmp_path / "no-vault") == ["y.md"]
