#!/usr/bin/env bash
# SessionStart: a few lines of orientation. Branch state, whether git hooks are
# active, the memory index, and a one-line next action (the `next` skill's
# local signals). Fails open.
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "?")
hooks=$(git config core.hooksPath 2>/dev/null || echo "")
echo "## Session start"
echo "- Branch: \`$branch\`$( [ "$branch" = main ] && echo ' (on main: create a branch before editing)')"
[ "$hooks" = ".githooks" ] || echo "- WARNING: git hooks are off. Run: git config core.hooksPath .githooks"
if [ -f .agents/memory/MEMORY.md ]; then
  n=$(grep -c '^- ' .agents/memory/MEMORY.md 2>/dev/null); n=${n:-0}
  echo "- Memory: $n note(s) indexed in .agents/memory/MEMORY.md (read the index; open notes that apply)"
fi
# One-line "what next" from local signals only (no network, so it stays instant).
[ -f .agents/skills/next/signals.py ] && python3 .agents/skills/next/signals.py --line 2>/dev/null </dev/null
exit 0
