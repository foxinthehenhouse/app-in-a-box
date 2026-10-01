---
name: backlog
description: The ticket → branch → PR flow. Use before starting build or fix work that will end in a PR (find or file the ticket and name the branch), whenever a bug, new scope or follow-up is discovered (file it immediately so nothing is lost), or when asked what to work on next.
---

# Backlog

The tracker is set in `appbox.yaml` → `stack.tracker` (`linear` or `github`). Linear
goes through the Linear MCP (authorise once: `/mcp` in Claude Code, `codex mcp login
linear` in Codex, then restart). If its tools aren't loaded this session, say so and
use the Linear web app link rather than dropping the ticket.

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

### Sub-tasks: capture them as you go

Work in progress uncovers more work. The moment you notice it, file it, don't
remember it:
- **Part of the current ticket** (a step you'll do in this PR, but worth tracking):
  a sub-issue. Linear: `save_issue` with `parentId` = the current ticket. GitHub:
  create the issue, then link it as a sub-issue (`gh api -X POST
  repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<new issue id>`),
  or add it to the parent's task list if sub-issues aren't enabled.
- **New scope, a bug or a follow-up** (not this PR): a new ticket, related to the
  current one, so the PR stays small.
- Say what you filed in one line ("Filed APP-58 as a follow-up: …"). At the end of a
  task, list every ticket you filed.

## Branch + PR

- Branch: `<type>/<ticket-id>-<kebab-slug>`, e.g. `feat/42-streak-home` or
  `fix/APP-17-otp-resend`. Types: `feat`, `fix`, `chore`, `docs`, `refactor`.
- Prefer a worktree (`new-worktree` skill) so parallel work never shares a checkout.
- PR title: `<type>: <summary> (#42)` (or `(APP-17)`). The `ticket` CI check fails a
  PR with no ticket id in its title, body or branch; `[no-ticket]` in the title is the
  escape, with the reason in the body.
- The PR body starts with `Closes #42` (GitHub) or the
  Linear id, so the tracker moves the ticket itself. Don't hand-move status.
- Open PRs as drafts until the gates are green, then run the `pr-review` skill.

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: Priority between tickets, and whether a discovered follow-up is in or out of the current scope. Recommend with a one-line reason each, let the owner pick, and file the answer in the tracker.
