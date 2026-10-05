---
name: next
description: Decide the single next best thing to work on, with two alternates. Reads setup progress, work in progress, open PRs and failing CI, the backlog (GitHub Issues or Linear), overdue harness rituals, product decisions parked until now, and north-star analytics if PostHog is connected. Use when someone asks "what next?", "what should I work on?", at the start of a session, or after a PR merges.
---

# Next

The owner shouldn't need to know what to ask for. This skill looks at everything and
proposes **one** action, plus two alternates, each with a one-line reason. It picks;
it doesn't start. The owner says "go" (or picks an alternate), and then you run the
skill it names.

## 1. Gather signals (deterministic first)

```bash
python3 .agents/skills/next/signals.py --remote
```

That returns JSON with setup progress, the current branch and work in progress, open
PRs with failing checks, failing CI on `main`, open issues, overdue rituals, and
`decisions_due`: product calls parked on day 0 in `design/brief.json` → `decisions`
whose phase has now arrived (the first feature, pre-launch, post-launch). If
`gh_available` is false, say so in one line and carry on with local signals.

Then add what the script can't read:
- **Linear** (`tracker: linear` in `appbox.yaml`): Linear MCP `list_issues` for the
  team, status Todo/In Progress, top 20 by priority.
- **North star** (if the PostHog MCP is connected): the funnel of the 5 events in
  `docs/product/BRIEF.md` over the last 7 days. Note the step with the biggest
  drop-off. If the MCP isn't connected, skip this and say "analytics not read".
- **In-flight specs:** `ls docs/product/specs/` for any spec whose ticket has no
  merged PR yet.

In Claude Code you may hand the CI-log and dependency reading to the `triage`
subagent (Haiku, cheap); in Codex, read them inline.

## 2. Rank (first match wins the top slot)

| Rank | Signal | Proposed action |
|---|---|---|
| 1 | Setup phase not done | Resume `new-app` at that phase |
| 2 | `main` CI failing | Fix it: `backlog` to file a `fix` ticket, then fix on a branch |
| 3 | Your open PR has failing checks or requested changes | `land` it: fixes CI and threads, then re-reviews |
| 4 | Uncommitted or unpushed work on a feature branch | Finish it: gates, then PR |
| 5 | Open PR with green CI, not yet reviewed | `land` it (runs `pr-review`, then merges or asks you) |
| 6 | Ritual overdue by 2× its cadence | Run that ritual (`reflect`, `harness-optimize`, `north-star-report`, `market-watch`) |
| 7 | Security or major dependency PR | `triage` it, then `pr-review` |
| 8 | A `p0` ticket, or the ticket at the funnel's worst step | `feature-discovery` on it (or `build-feature` if it's specced) |
| 9 | A decision is due (`decisions_due`) | Ask it as one structured question, the `docs/DEFAULTS.md` answer recommended, and write the answer back to its ledger entry; `pre-launch` ones go to `ship` |
| 10 | Next ticket by priority (`p0` > `p1` > `p2`, `ready` first) | `feature-discovery` / `build-feature` |
| 11 | Empty backlog | `north-star-report` to find the biggest drop-off, then file tickets |

Tie-break: the thing closest to users (a broken build beats a new feature), then the
cheapest to finish. Never propose starting new work while one of your PRs is red.

## 3. Answer (exactly this shape, under 12 lines)

The `Next:` line always names the skill in parentheses. An action without its skill
leaves the owner asking "how?".
Exactly two alternates. Nothing goes after the `Signals read` line except the
question: no "after that…" or "also pending" list, because a fourth option dilutes the pick.

```
Next: <action> (<skill to run>, e.g. `/feature-discovery #14` or `$feature-discovery #14`)
Why: <the signal, with its number: PR #, run, ticket, funnel step and %>

Or:
2. <alternate>: <one-line why>
3. <alternate>: <one-line why>

Signals read: setup ✓ · PRs ✓ · CI ✓ · backlog ✓ · rituals ✓ · decisions ✓ · analytics ✗ (PostHog not connected)
```

Use a structured question (`AskUserQuestion` in Claude Code, `request_user_input` in
Codex) with the three options if the tool exists, otherwise ask in chat. On "go", run
the named skill. If you find a bug or scope while gathering signals, file it with
`backlog` before answering. Don't keep a to-do list in chat.

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: When two actions tie on rank, or the top one is a product call (a scope cut, launching, pricing), present the pick and alternates as one structured question instead of starting.
