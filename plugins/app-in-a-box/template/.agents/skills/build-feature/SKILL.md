---
name: build-feature
description: Implement an approved feature spec end to end on its own branch/worktree. Migration → backend endpoint + tests → mobile adapter + screen + analytics → gates → E2E flow → PR → review. Use after feature-discovery has produced an approved spec, or when asked to build a specced ticket.
argument-hint: "<spec path or ticket id>"
---

# Build feature

Input: an approved spec in `docs/product/specs/`. No spec means you run
`feature-discovery` first.

**Claude Code accelerators (optional, both cost more tokens):**
- *Thorough mode:* the `build-feature` Workflow (`.claude/workflows/build-feature.js`)
  runs this same order as a script: plan, tests first, backend and mobile in parallel,
  break-it self-review, draft PR, then the `pr-review` workflow. Use it only when the
  owner asks for it.
- *Several specced tickets at once:* spawn one background subagent per ticket with
  `isolation: worktree`, so each builds in its own checkout, and review each PR as it
  lands. In Codex, run tickets one after another (or in separate `codex --worktree`
  sessions).

## Order of work (each step verified before the next)

1. **Branch:** `new-worktree` skill → `feat/<ticket>-<slug>`.
2. **Tests first where it's cheap:** write the FR→TC tests from the spec's test plan
   (backend pytest; pure mobile logic in jest). Watch them fail.
3. **Migration** (if any): new timestamped file, additive, RLS, rollback in header.
4. **Backend:** service (pure logic) → router (I/O, `get_current_user`, scoped by
   `user.id`) → `Wire` response model. `scripts/dev-venv.sh python -m pytest -q`.
5. **Mobile:** `*Wire` type + adapter in `lib/api.ts` → screen from `components/ui`
   primitives + theme tokens → analytics helpers (view event, success+failure) → honest
   loading/empty/error states → testIDs. `cd mobile && npm run gates`.
6. **E2E:** add or extend a Maestro flow under `mobile/.maestro/` for the happy path.
7. **Self-review:** re-read your diff as a hostile reviewer. What would break for a
   user on last month's app build? What if the request comes from a different user?
   What if the user taps twice on a slow network? For each important test, **break
   the code on purpose** (drop the filter, pick the wrong row, skip a field) and
   confirm the test goes red. A test whose fixture can't tell right from wrong
   (e.g. "latest by X" where X and list order agree) proves nothing.
8. **Context:** update `AGENTS.md` → "Where things live" (a new screen, router,
   service or table gets its row; the harness lint fails CI otherwise), and any
   rule or product line this feature made untrue. Future agents read this first.
9. **PR:** draft PR, body = spec link + what changed + how it was verified (real
   command output). Then run the `land` skill, which reviews (`pr-review`), fixes, waits on CI
   and merges. After it merges, run `next`.

## Never

- Weaken or delete a test to get green.
- Change a wire field in place (add alongside).
- Claim done on code you didn't run.
- Widen scope silently. File a ticket for anything you notice and keep going.

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: Anything the spec didn't settle that a user would notice: an extra state or screen, cutting an acceptance criterion, copy, a default value, a limitation you'd ship with. Stop and ask before building it, not in the PR afterwards. Pure implementation choices stay yours.
