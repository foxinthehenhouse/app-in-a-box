#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit): an explicit "are you sure?" before editing a
high-blast-radius file.

Not a hard block (bash-safety.sh does that for shell commands). It emits
permissionDecision "ask" so a human approves edits where a mistake is expensive or
irreversible: DB migrations, secrets, Expo/EAS build config, CI workflows, native
Google/Firebase config, dependency lock files. Every other file passes silently.

`.env.example` (any `*.example`) is exempt on purpose: it holds names, not values, and
documenting a new variable there is exactly what the env-var-wiring rule asks for.

Fails open: any parse/IO error -> allow (exit 0, no output).
Pinned by tests/harness/test_sensitive_files_hook.py.
"""

from __future__ import annotations

import json
import os
import sys

# Substring match against the repo-relative path -> directory-scoped blast radius.
DIR_NEEDLES = [
    (
        "supabase/migrations/",
        "a database migration. Schema changes are effectively irreversible once applied. "
        "Editing an already-applied migration is almost never right: add a NEW timestamped "
        "migration, and verify the LIVE schema with a select rather than trusting the ledger.",
    ),
    (
        ".github/workflows/",
        "a CI workflow. Changes affect every PR and build, can leak secrets, and burn minutes.",
    ),
]

# Exact basename match -> file-scoped blast radius.
BASENAMES = {
    "eas.json": "the EAS build config: every build channel and the release train.",
    "app.config.ts": "the Expo app config (bundle id, entitlements, plugins): the whole native build.",
    "app.json": "the Expo app config: the whole native build.",
    "GoogleService-Info.plist": "native Google/Firebase config: auth and push provisioning.",
    "google-services.json": "native Google/Firebase config: auth and push provisioning.",
    "package-lock.json": "a dependency lock. Regenerate it with npm, don't hand-edit.",
    "yarn.lock": "a dependency lock. Regenerate it with yarn, don't hand-edit.",
    "pnpm-lock.yaml": "a dependency lock. Regenerate it with pnpm, don't hand-edit.",
    "Podfile.lock": "a dependency lock. Regenerate it with pod install, don't hand-edit.",
    "uv.lock": "a dependency lock. Regenerate it with uv, don't hand-edit.",
    "poetry.lock": "a dependency lock. Regenerate it with poetry, don't hand-edit.",
}


def reason_for(rel: str) -> str | None:
    """Why `rel` (repo-relative path) needs confirmation, or None when it doesn't."""
    base = os.path.basename(rel)
    for needle, why in DIR_NEEDLES:
        if needle in rel:
            return why
    if base in BASENAMES:
        return BASENAMES[base]
    if (base == ".env" or base.startswith(".env.")) and not base.endswith(".example"):
        return "an environment/secrets file. Never put a real secret in a commit."
    return None


def decision(event: dict, root: str) -> dict | None:
    """The hook's JSON output for one tool event, or None to stay silent."""
    ti = event.get("tool_input") or {}
    fp = str(ti.get("file_path") or ti.get("path") or "")
    if not fp:
        return None
    rel = fp[len(root) :].lstrip("/") if root and fp.startswith(root) else fp
    if rel.startswith("./"):
        rel = rel[2:]
    why = reason_for(rel)
    if not why:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"`{rel}` is {why}\nConfirm this edit is intended before proceeding."
            ),
        }
    }


def main() -> int:
    try:
        event = json.load(sys.stdin)
        out = decision(event, os.environ.get("CLAUDE_PROJECT_DIR", ""))
    except Exception:
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
