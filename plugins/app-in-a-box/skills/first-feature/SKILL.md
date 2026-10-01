---
name: first-feature
description: Phase 8 of App in a Box. Turns the product brief into a seeded backlog (5–10 tickets), then builds feature #1 through the full feature-discovery → build-feature → pr-review loop, so the user sees the whole way of working once, end to end.
---

# Phase 8: First feature

## 1. Seed the backlog

From `docs/product/BRIEF.md`, file 5–10 tickets with the project's `backlog` skill:
- 1 ticket per v1 screen or core-loop step not already built by the scaffold
- 1 for "north-star dashboard in PostHog" (funnel of the 5 key events)
- 1 for Apple/Google sign-in (if chosen in the interview but deferred)
- 1 for "TestFlight / internal testing build" (`eas build --profile preview`)
Label priorities. The core loop is `p0`.

## 2. Pick feature #1 with the user

Recommend the `p0` ticket that completes the core loop, the smallest thing that lets
a real user do the core action and see feedback. Ask (structured) to confirm.

## 3. Run the loop, narrating each step in one line

1. `feature-discovery` → spec in `docs/product/specs/`. Show the owner the
   Problem/Scope/UX and get a yes.
2. `build-feature` → worktree, tests, migration, API, screen, analytics, gates, PR.
3. `pr-review` → verdict comment.

## 4. Hand-off

Close with the summary the orchestrator describes (app on phone, links, "what I need
from you", final progress checklist). Then run the orchestrator's **Keep going**
section (`KIT/skills/new-app/SKILL.md`): the repo's `next` skill picks feature #2 (or
whatever matters more, e.g. a red CI run), and `routines` is offered once. Tell them
the habit that matters most:

> Open the project and ask "what's next?". Describe what you want in plain words and
> the harness routes it: `feature-discovery` → `build-feature` → `pr-review`. Every
> change goes through a ticket, a branch and a reviewed PR.

Set `progress.first_feature: done` after the hand-off.
