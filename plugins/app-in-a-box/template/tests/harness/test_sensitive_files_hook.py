"""warn-sensitive-files.py asks before a high-blast-radius edit and says nothing otherwise.

A PreToolUse hook that emits `permissionDecision: "ask"` for migrations, workflows, build
config, lock files and `.env*`. The two ways it fails silently: a path that should ask and
doesn't (regression in the needles), and a hook that asks for everything (gets switched
off within a day). Both directions are pinned, through the real hook and its pure core.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import pytest
from harness_lib import HOOKS_DIR

HOOK = HOOKS_DIR / "warn-sensitive-files.py"


def _load():
    spec = importlib.util.spec_from_file_location("warn_sensitive_files", HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load()


def run_hook(stdin: str, root: str = "/r") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": root},
        timeout=30,
    )


def test_migration_edit_asks() -> None:
    out = run_hook(json.dumps({"tool_input": {"file_path": "/r/supabase/migrations/001_x.sql"}}))
    assert out.returncode == 0
    d = json.loads(out.stdout)["hookSpecificOutput"]
    assert d["permissionDecision"] == "ask" and d["hookEventName"] == "PreToolUse"
    assert "supabase/migrations/001_x.sql" in d["permissionDecisionReason"]


def test_component_edit_is_silent() -> None:
    out = run_hook(json.dumps({"tool_input": {"file_path": "/r/mobile/components/Card.tsx"}}))
    assert out.returncode == 0 and out.stdout == ""


def test_garbage_stdin_fails_open() -> None:
    out = run_hook("not json at all")
    assert out.returncode == 0 and out.stdout == ""


@pytest.mark.parametrize(
    "rel",
    [
        "supabase/migrations/20260101_init.sql",
        ".github/workflows/ci.yml",
        "mobile/eas.json",
        "mobile/app.json",
        "mobile/app.config.ts",
        "mobile/package-lock.json",
        "mobile/ios/Podfile.lock",
        "uv.lock",
        ".env",
        ".env.local",
        "mobile/.env.production",
        "mobile/GoogleService-Info.plist",
    ],
)
def test_sensitive_paths_ask(rel: str) -> None:
    assert hook.reason_for(rel), rel


@pytest.mark.parametrize(
    "rel",
    [
        "backend/main.py",
        "mobile/app/(app)/index.tsx",
        "mobile/components/Card.tsx",
        ".env.example",
        "mobile/.env.example",
        "docs/env.md",
        "mobile/package.json",
        "supabase/seed.sql",
        ".github/dependabot.yml",
        "tests/harness/test_x.py",
    ],
)
def test_ordinary_paths_are_silent(rel: str) -> None:
    assert hook.reason_for(rel) is None, rel


def test_root_prefix_is_stripped_before_matching() -> None:
    ev = {"tool_input": {"file_path": "/r/.github/workflows/ci.yml"}}
    out = hook.decision(ev, "/r")
    assert (
        out
        and "`.github/workflows/ci.yml`" in out["hookSpecificOutput"]["permissionDecisionReason"]
    )
    assert hook.decision({"tool_input": {"path": "./mobile/eas.json"}}, "") is not None
    assert hook.decision({"tool_input": {}}, "/r") is None
