---
name: new-worktree
description: Create an isolated git worktree + branch off origin/main for one unit of work, so parallel agents or sessions never share a checkout. Use when starting any ticket, or when another session may be working in the main checkout.
---

# New worktree

One unit of work = one branch = one worktree = one PR. The primary checkout stays on
`main`.

```
git fetch origin main
```

```
git worktree add .claude/worktrees/<id> -b <type>/<ticket>-<slug> origin/main
```

Then, inside the worktree:
- `scripts/dev-venv.sh` (reuses the shared Python venv instantly)
- `cd mobile && npm install` (node_modules is per-worktree)
- copy env files: `cp ../../../.env .env` and `cp ../../../mobile/.env mobile/.env`
  (from the worktree root; they're gitignored, so they aren't in the new checkout)
- `git config core.hooksPath .githooks` (hooks path is per-clone config, shared by
  worktrees; this just confirms it)

Tell the user the worktree path; the session should `cd` there. When the PR merges:
`git worktree remove .claude/worktrees/<id>`, then `git branch -d <branch>`. Lower-case
`-d` refuses a branch that isn't merged, which is the point; never `-D`.
