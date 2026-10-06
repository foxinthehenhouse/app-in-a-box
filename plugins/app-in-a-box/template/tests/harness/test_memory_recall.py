"""The memory-recall hook points at files that exist.

`.claude/hooks/memory_recall.py` surfaces up to three memory notes per prompt as paths.
It once rendered them as `.claude/memory/<note>` while reading `.agents/memory/`, so every
recall was a dead link and nobody opened a note for weeks: the hook ran, printed, and
helped nothing. The rule: every path the hook prints must exist relative to the project
root it was run from. The REAL hook runs here (copied into a throwaway project so the
`__file__`-relative resolution is exercised), and a copy with the old prefix must fail.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from harness_lib import HOOKS_DIR

HOOK = HOOKS_DIR / "memory_recall.py"
POINTER = re.compile(r"^- `([^`]+)`", re.M)

# Ten notes: BM25's idf needs a population, and the target must out-score the field.
TARGET = """---
title: Sign-in redirect loop
description: Why the sign-in redirect looped after Supabase auth and how routing fixed it
tags: [auth, supabase, redirect, routing]
---
The sign-in redirect looped because the guard replaced the route with a bare group.
Let the auth guard's redirect route after Supabase sign-in instead.
"""
FILLER = [
    ("push_tokens", "Expo push tokens expire; refresh on launch."),
    ("migration_ledger", "Verify the live schema, not the migration ledger."),
    ("eas_channels", "Preview and production channels need their own env blocks."),
    ("analytics_masking", "Session replay is masked; the event trail is the record."),
    ("worktree_layout", "One branch, one worktree, one PR."),
    ("lock_files", "Regenerate lock files with the package manager."),
    ("rls_policies", "Every new table ships with row level security."),
    ("rate_limits", "The nutrition endpoint is rate limited per user."),
    ("tab_bar_web", "The web tab bar must not cover screen titles."),
]


def seed_project(root: Path, hook_src: str) -> Path:
    (root / ".claude" / "hooks").mkdir(parents=True)
    hook = root / ".claude" / "hooks" / "memory_recall.py"
    hook.write_text(hook_src)
    mem = root / ".agents" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("# Memory index\n")
    (mem / "sign_in_redirect_loop.md").write_text(TARGET)
    for name, body in FILLER:
        (mem / f"{name}.md").write_text(f"---\ntitle: {name}\n---\n{body}\n")
    return hook


def run_hook(hook: Path, prompt: str, tmp: Path) -> str:
    event = {"prompt": prompt, "session_id": uuid.uuid4().hex}
    out = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "TMPDIR": str(tmp)},
        timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def pointer_problems(output: str, root: Path) -> list[str]:
    """Every `- \\`path\\`` line must name a file under `root`."""
    return [p for p in POINTER.findall(output) if not (root / p).is_file()]


PROMPT = "why does the sign-in redirect loop after supabase auth, is it the routing"


def test_real_hook_recalls_the_seeded_note_and_every_pointer_exists(tmp_path: Path) -> None:
    hook = seed_project(tmp_path, HOOK.read_text(encoding="utf-8"))
    out = run_hook(hook, PROMPT, tmp_path)
    assert "sign_in_redirect_loop.md" in out, f"the matching note was not recalled:\n{out}"
    assert pointer_problems(out, tmp_path) == []


def test_hook_stays_quiet_on_an_unrelated_prompt(tmp_path: Path) -> None:
    hook = seed_project(tmp_path, HOOK.read_text(encoding="utf-8"))
    assert run_hook(hook, "add a kebab-case slug validator to the settings screen", tmp_path) == ""


def test_the_old_prefix_fails(tmp_path: Path) -> None:
    """Negative control: the bug as shipped. Same notes, same prompt, pointers rendered
    under `.claude/memory/` -> every pointer is a 404 and the check says so."""
    src = HOOK.read_text(encoding="utf-8")
    assert (
        src.count('".agents/memory/{p.name}"') == 1
    ), "the pointer prefix moved; update this control"
    bugged = src.replace('".agents/memory/{p.name}"', '".claude/memory/{p.name}"')
    hook = seed_project(tmp_path, bugged)
    out = run_hook(hook, PROMPT, tmp_path)
    assert POINTER.findall(out), "control produced no pointers; it proves nothing"
    assert pointer_problems(out, tmp_path), "a dead pointer passed the existence check"


def test_pointer_rule_can_fail_on_text_alone(tmp_path: Path) -> None:
    (tmp_path / "real.md").write_text("x")
    assert pointer_problems("- `real.md` — ok\n", tmp_path) == []
    assert pointer_problems("- `real.md` — ok\n- `ghost.md` — gone\n", tmp_path) == ["ghost.md"]


def test_copy_tool_is_not_the_hook() -> None:
    """Sanity: the hook under test is the one settings.json registers, not a stale copy."""
    assert HOOK.is_file()
    assert shutil.which("bash")
