#!/usr/bin/env bash
# Stop hook: seed a pending-reflection file when a session did substantive work.
# The `reflect` skill consumes it (and deletes it); the SessionStart healthcheck
# escalates if it sits unconsumed past the reflect cadence. This is what makes
# memory-writing a habit rather than a hope.
#
# The seed lives in the per-project state dir (harness_paths.pending_reflection_file),
# outside the repo, so it never dirties a branch. Prints nothing. Fails open.

set -u

INPUT=$(cat 2>/dev/null || echo "{}")
command -v python3 >/dev/null 2>&1 || exit 0
PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0

field() {
  printf '%s' "$INPUT" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    v = d.get(sys.argv[1], "") if isinstance(d, dict) else ""
    print(v if isinstance(v, (str, bool, int)) else "")
except Exception:
    print("")
' "$1" 2>/dev/null || echo ""
}

# Re-entry guard: never recurse inside a Stop-hook continuation.
[ "$(field stop_hook_active)" = "True" ] && exit 0

cd "$PROJECT_ROOT" 2>/dev/null || exit 0
TOUCHED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
RECENT=$(git log --since="6 hours ago" --oneline 2>/dev/null | wc -l | tr -d ' ')
# Seed only after real work: 3+ files touched, or a commit in the last 6h.
[ "${TOUCHED:-0}" -ge 3 ] || [ "${RECENT:-0}" -ge 1 ] || exit 0

SEED=$(PROJECT_ROOT="$PROJECT_ROOT" python3 -c '
import os, sys
sys.path.insert(0, sys.argv[1])
from harness_paths import pending_reflection_file
print(pending_reflection_file(os.environ["PROJECT_ROOT"]))
' "$HOOK_DIR" 2>/dev/null) || exit 0
[ -n "$SEED" ] || exit 0
mkdir -p "$(dirname "$SEED")" 2>/dev/null || exit 0

TS=$(date -u +"%Y-%m-%d %H:%M UTC")
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
CHANGED=$(git status --porcelain 2>/dev/null | head -20 | sed 's/^/  /')
COMMITS=$(git log --since="6 hours ago" --pretty=format:"  %h %s" 2>/dev/null | head -5)
SESSION_ID=$(field session_id)

cat > "$SEED" 2>/dev/null <<EOF || true
# Pending reflection: seeded by session-reflect.sh at ${TS}

A session on \`${BRANCH}\` in ${PROJECT_ROOT} touched ${TOUCHED} file(s). The
\`reflect\` skill consumes this seed: decide whether anything is worth a note in
\`.agents/memory/\` (a correction, a trap that cost time, a decision and its reason).
Nothing notable: just delete this file. Never memorise code patterns, paths, or
anything \`git log\` already says.

## Files touched
${CHANGED:-  (working tree clean)}

## Recent commits (last 6h)
${COMMITS:-  (none)}

## Session
${SESSION_ID:-unknown}
EOF

exit 0
