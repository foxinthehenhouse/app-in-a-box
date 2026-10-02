#!/usr/bin/env bash
# SessionStart: a few lines of orientation. Branch state, whether git hooks are
# active, the memory index (its BODY, not a count: an index you have to go and read
# is an instruction, an index already in context is a mechanism), and a one-line
# next action (the `next` skill's local signals). Fails open.
# Pinned by tests/harness/test_session_start.py.
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "?")
hooks=$(git config core.hooksPath 2>/dev/null || echo "")
echo "## Session start"
echo "- Branch: \`$branch\`$( [ "$branch" = main ] && echo ' (on main: create a branch before editing)')"
# A branch with no ticket id cannot be tracked by the ticket CI check or the tracker's
# PR integration. Ids look like ABC-12 (Linear) or 42- / #42- (GitHub Issues).
case "$branch" in
  main|master|\?) ;;
  *)
    if ! printf '%s' "$branch" | grep -Eq '([A-Za-z]{2,6}-[0-9]+|#?[0-9]+-)'; then
      echo "- WARNING: branch \`$branch\` carries no ticket id (ABC-12 or 42-). Every change has a ticket: the \`backlog\` skill files one and names the branch."
    fi ;;
esac
[ "$hooks" = ".githooks" ] || echo "- WARNING: git hooks are off. Run: git config core.hooksPath .githooks"
if [ -f .agents/memory/MEMORY.md ]; then
  n=$(grep -c '^- ' .agents/memory/MEMORY.md 2>/dev/null); n=${n:-0}
  echo "- Memory: $n note(s) indexed in .agents/memory/MEMORY.md. The index follows; open a linked note when its line applies."
  # Bounded by construction: the reflect skill keeps the index at <= 45 entries, and
  # head caps it at 80 lines / 12 KB even if it hasn't run.
  head -c 12288 .agents/memory/MEMORY.md | head -80 | sed 's/^/    /'
fi
# One-line "what next" from local signals only (no network, so it stays instant).
[ -f .agents/skills/next/signals.py ] && python3 .agents/skills/next/signals.py --line 2>/dev/null </dev/null
exit 0
