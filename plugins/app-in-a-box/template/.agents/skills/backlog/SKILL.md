---
name: backlog
description: The ticket → branch → PR flow. Use before starting build or fix work that will end in a PR (find or file the ticket and name the branch), whenever a bug, new scope or follow-up is discovered (file it immediately so nothing is lost), or when asked what to work on next.
---

# Backlog

The tracker is set in `appbox.yaml` → `stack.tracker` (`github` or `linear`).

## Pick what's next

- GitHub: `gh issue list --state open --label ready --limit 20` (fall back to all open
  issues sorted by priority label: `p0` > `p1` > `p2`).
- Linear: use the Linear MCP `list_issues` for the project's team, status "Todo".
Suggest the top 1–3 with one line each on why, and let the owner pick.

## File a ticket (the moment you notice scope, a bug or a follow-up)

Title: imperative, specific ("Show streak count on Home"). Body:

```
## Problem
## Acceptance criteria
- [ ] ...
## Notes / links
```

GitHub: `gh issue create --title ... --body ... --label <type>,<priority>`.
Linear: MCP `save_issue`. Never keep a backlog in a chat thread or a scratch file.

## Branch + PR

- Branch: `<type>/<ticket-id>-<kebab-slug>`, e.g. `feat/42-streak-home` or
  `fix/APP-17-otp-resend`. Types: `feat`, `fix`, `chore`, `docs`, `refactor`.
- Prefer a worktree (`new-worktree` skill) so parallel work never shares a checkout.
- PR title: `<type>: <summary> (#42)`. Body starts with `Closes #42` (GitHub) or the
  Linear id, so the tracker moves the ticket itself. Don't hand-move status.
- Open PRs as drafts until the gates are green, then run the `pr-review` skill.
