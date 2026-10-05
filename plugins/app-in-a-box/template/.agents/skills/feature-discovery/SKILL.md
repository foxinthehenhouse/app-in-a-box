---
name: feature-discovery
description: The discovery → definition front half for any new feature. Investigates the real codebase and product brief from product, design and engineering angles, then writes a right-sized PRD + design brief + tech spec before any code. Use when someone asks for a new feature or capability, a PRD, requirements, or to scope or spec something. Hands off to build-feature.
argument-hint: "<feature idea or ticket id>"
---

# Feature discovery

Don't jump to code off a one-line idea. Twenty minutes here saves days of rework.

## 1. Ground it

- Read `docs/product/BRIEF.md` (core loop, north star, out-of-scope list).
- Read `design/brief.json` → `decisions`: any `deferred` decision whose phase has
  arrived (`next`'s `decisions_due` lists them; on the first feature that's the
  `first-feature` ones: the nudge policy and when to ask for each permission) and any
  this feature touches. Read `docs/DEFAULTS.md` for the calls already made (permission
  priming after the payoff, at most one notification a day, the review prompt…).
- Find or file the ticket (`backlog` skill).
- Read the code the feature touches: screens, `lib/api.ts` adapters, routers, tables.
  Note what already exists that can be reused.

## 2. Three perspectives

In Claude Code, spawn `product-manager`, `ux-designer` and `lead-engineer` as
parallel subagents, each with the brief, the ticket and the code you found in step 1;
they return findings and `⚖️ QUESTION:` blocks, and you ask the owner. In Codex, take
the three views one after another.

- **Product:** what user problem, which step of the core loop, how we'll know it
  worked (which event moves which metric), what's explicitly out of scope.
- **Design:** the screens/states (loading, empty, error, success), copy in the
  project's voice, accessibility notes, judged against `docs/design/TASTE.md` (the
  rubric the prototype passed). For a real UI fork, render 2 options as HTML mockups
  and ask the owner. Don't pick silently.
- **Engineering:** data model changes (additive migration + RLS), endpoints (wire
  shape, auth, `user_id` scoping), mobile adapter, analytics events (success +
  failure), env vars/feature config, test plan, risks.

## 3. Write the spec (one file, right-sized)

`docs/product/specs/<ticket>-<slug>.md`:

```
# <Feature>  (<ticket>)
## Problem & outcome   (who, what changes for them, metric)
## Scope / Out of scope
## UX                  (screens + states; mockup link if any)
## Data & API          (migration, endpoint + request/response shape, Wire type)
## Analytics           (event names + props, success+failure pairs)
## Requirements        FR-01… each testable
## Test plan           TC-01… mapped to FRs; include one E2E flow if UI changes
## Risks & ⚖️ decisions for the owner
```

A small feature is half a page. Don't pad.

## 4. Gate

Show the owner the Problem/Scope/UX/⚖️ sections (not the whole spec) and get a yes.
Ask the due decisions from step 1 in the same structured round, each with the
`docs/DEFAULTS.md` answer as the recommended option, and write each answer back to its
ledger entry (`status: asked`, or `default` if they took the recommendation).
Then hand off: "Run `build-feature <spec path>`."

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: Scope in and out of v1, which user problem wins when two conflict, copy and tone of new screens, any new personal data collected, and the success metric. Ask them together once discovery is done, before the PRD is final; the PRD records each answer.
