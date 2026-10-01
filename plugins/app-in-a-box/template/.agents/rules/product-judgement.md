---
description: Product-judgement calls belong to the owner; ask them with a structured question, never decide silently
globs: docs/product/**, mobile/app/**, mobile/locales/**, mobile/components/**
---
Agents own the mechanics. **The owner owns product judgement.** When a task reaches a
call below, stop and ask; don't pick one and mention it afterwards.

## What counts (ask)

- **Scope:** adding, cutting or deferring anything the ticket or spec didn't settle.
- **What users see or read:** copy and tone, onboarding steps, empty and error
  states, notification wording and frequency, anything that changes a flow.
- **Money:** pricing, paywalls, trials, anything that costs the owner money.
- **Positioning:** naming, the angle against competitors, who the app is for.
- **Data and trust:** collecting new personal data, sharing it, retention, a
  privacy tradeoff.
- **Priorities:** which of two tickets goes first; accepting a known limitation.
- **Measures:** changing the north-star metric, the 5 key events, or what counts as
  success.
- **Anything irreversible** (a migration that drops data, a public API shape, a
  store listing).

## What doesn't (just do it)

An implementation detail with a clear right answer, a convention these docs already
set, anything a test or linter decides, or a fact you can look up. Asking those
wastes the owner's attention, which is the scarcest thing in the project.

## How to ask

- **Structured, both agents.** Claude Code: `AskUserQuestion`. Codex:
  `request_user_input` if available, otherwise a numbered list in chat, then wait.
  Give 2–3 options, the **recommended one first, marked "(Recommended)"**, a one-line
  tradeoff on each, and a "you pick" way out.
- **Batch.** Collect the calls in a task and ask them together at a natural
  checkpoint (after discovery, before building, before merging), not one per minute.
- **Show evidence.** Link what drives the recommendation: the brief, VALIDATION.md,
  analytics, a competitor. For anything visual, show a rendered mockup, not
  adjectives.
- **Subagents can't ask.** They return a block and the orchestrating agent asks it:
  `⚖️ QUESTION: <question> · Options: A (Recommended) / B / C · Why: <evidence>`.
- **Unattended runs** (CI review, Routines, cron): never decide. Post the ⚖️ question
  in the PR or issue, continue only with work that doesn't depend on the answer, and
  say what's waiting on it.

## Record the answer

A call that sets precedent or can't be undone gets a line in `docs/decision-log.md`
(date, the question, the options, the choice, who chose). In specs and PR bodies,
mark calls you made within already-given authority with ⚖️ and name the
alternative, so the owner can still overrule them.
