#!/usr/bin/env python3
"""PreToolUse(Edit|Write|MultiEdit) — path-scoped rule injector.

Ports the "path-scoped rules" pattern (Cursor-style .rules) to Claude Code's hook
model: when you edit a file whose path matches a rule's `globs:`, that rule's body
is injected as additionalContext at that exact moment — so domain rules load when
relevant (not as a permanent wall of context) and can't be lost to summarization.

Rules live in `.agents/rules/*.md` (shared with Codex via AGENTS.md) with frontmatter:

    ---
    description: one-line summary
    globs: backend/models/**, mobile/lib/api.ts
    ---
    <markdown body — the rule the model should read before editing>

To avoid re-injecting the same rule on every edit, each rule fires at most once
per session (keyed by session_id). Fail open on any error.
"""
import glob
import json
import os
import re
import sys
import tempfile


def read_event():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def glob_to_re(pat):
    pat = pat.strip()
    out, i = [], 0
    while i < len(pat):
        if pat[i:i + 2] == "**":
            out.append(".*")
            i += 2
            if i < len(pat) and pat[i] == "/":
                i += 1  # `**/` also matches zero directories
        elif pat[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pat[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def parse_rule(path):
    try:
        text = open(path).read()
    except Exception:
        return None
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return None
    fm, body = m.group(1), m.group(2).strip()
    gm = re.search(r"^globs:\s*(.+)$", fm, re.M)
    if not gm or not body:
        return None
    raw = [g.strip() for g in re.split(r"[,\s]+", gm.group(1).strip()) if g.strip()]
    # A pattern starting with `!` EXCLUDES (gitignore-style).
    globs = [g for g in raw if not g.startswith("!")]
    excludes = [g[1:] for g in raw if g.startswith("!") and len(g) > 1]
    return {"globs": globs, "excludes": excludes, "body": body}


def main():
    ev = read_event()
    ti = ev.get("tool_input", {}) or {}
    fp = ti.get("file_path", "") or ti.get("path", "")
    if not fp:
        sys.exit(0)

    root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    rel = fp[len(root):].lstrip("/") if fp.startswith(root) else fp
    if rel.startswith("./"):
        rel = rel[2:]

    rules_dir = os.path.join(root, ".agents", "rules")
    if not os.path.isdir(rules_dir):
        sys.exit(0)

    # Once-per-session-per-rule dedupe so a busy edit loop isn't spammed.
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(ev.get("session_id", "nosession")))
    marker = os.path.join(tempfile.gettempdir(), f"appbox-pathrules-{sid}.json")
    try:
        fired = set(json.load(open(marker)))
    except Exception:
        fired = set()

    out, changed = [], False
    for rf in sorted(glob.glob(os.path.join(rules_dir, "*.md"))):
        name = os.path.basename(rf)
        if name == "README.md" or name in fired:
            continue
        rule = parse_rule(rf)
        if not rule:
            continue
        if any(glob_to_re(g).match(rel) for g in rule["globs"]) and not any(
            glob_to_re(g).match(rel) for g in rule.get("excludes", [])
        ):
            out.append(f"**Path rule ({name})** — applies to `{rel}`:\n\n{rule['body']}")
            fired.add(name)
            changed = True

    if changed:
        try:
            json.dump(sorted(fired), open(marker, "w"))
        except Exception:
            pass

    if out:
        ctx = "\n\n---\n\n".join(out)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": ctx}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
