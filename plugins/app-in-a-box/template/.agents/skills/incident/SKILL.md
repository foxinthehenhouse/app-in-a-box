---
name: incident
description: Production incident response. Walks docs/runbooks/incident.md step by step, proposes the rollback (or kill switch) FIRST when a release lines up with the start, then traces the failure from error_id / request_id to the line of code, ships the fix, and drafts the postmortem with the guard it added. Use when the app or API is down, broken, crashing or slow for users, when a Sentry alert fires, when /health says degraded, or when someone says "something is wrong in production".
argument-hint: "[what users see, an error code, or a Sentry link]"
---

# Incident

Stop the bleeding first, understand it second. Most incidents start with a release,
and rolling that release back takes a minute while a diagnosis takes an hour. So this
skill finds what changed and proposes undoing it **before** it reads a single stack
trace. The runbook is `docs/runbooks/incident.md`; this walks it in order and keeps a
timeline as it goes (times in UTC, for the postmortem).

## 1. Is it live, and how big? (2 minutes)

```bash
curl -s "$API_URL/health?deep=1"     # status, db, features_unavailable (a missing env var shows by name)
```

Then the size: Sentry issue (users affected, trend, which release), PostHog
`api_failed` by `path` / `status` over the last hour, and the crash-free rate of the
newest release. Set a severity from the runbook's table (SEV1 data exposure or
everyone broken, SEV2 a core flow broken for some, SEV3 degraded with a workaround).

## 2. What changed? Propose the rollback first

List every change in the window before the first signal, newest first:

| Layer | How to see it |
|---|---|
| OTA update | `cd mobile && eas update:list --branch production --limit 5` (a staged rollout shows its %) |
| API deploy | `railway deployment list`, or `/health` `version` against `git log --oneline -5 origin/main` |
| Migration | `ls -t supabase/migrations/ \| head -3` and its merge time |
| Flags | PostHog feature-flag history; `FLAG_*` variables on Railway |

**If one lines up with the start, propose undoing it now, before any diagnosis.**
Name the exact command from `docs/runbooks/rollback.md`:

- OTA: `scripts/rollback-ota.sh` (it plans first; it reverts a staged rollout instead
  of publishing over it), then `scripts/rollback-ota.sh --yes -m "<reason>"`.
- API: `railway redeploy --deployment <last good id>`, then confirm `/health` `version`.
- A feature behind a kill switch (`kill-*` in `mobile/lib/flags.ts` /
  `backend/flags.py`): turn that flag ON in PostHog (both app and API read it), or set
  `FLAG_KILL_<NAME>=1` on Railway if PostHog itself is the problem.
- A migration: usually roll the API back and leave the schema (migrations are
  additive); the runbook covers the rare real undo.

Ask with a structured question: the rollback **(Recommended)**, fix forward, or keep
investigating. Run it only on a yes. Afterwards confirm it worked: the Sentry issue
stops getting events for the new release, `/health` is ok, the funnel recovers.

If nothing lines up (no change in the window), say so and go to step 3: a
rollback with no suspect is a guess.

## 3. Find the line of code

1. Start from an id: the `error_id` the user read out (the error screen shows it), a
   Sentry issue, or a time.
2. Sentry → `error_id:<id>` → stack trace, release, `request_id` tag. Events are
   scrubbed by design (no bodies, user data or exception messages).
3. Railway logs carry `[<request_id>]` on every line (`@request_id:<id>` with
   `LOG_FORMAT=json`). The request id is also the trace id: the app's `traceparent`
   uses the request id without its dashes, so a sampled request (5% by default) has a
   Sentry trace with its spans under that id.
4. Reproduce it in a test that fails before the fix (the filter-honouring fakes in
   `tests/test_prod_fakes.py`, a jest test for app code).

## 4. Fix forward

File it with the `backlog` skill (a `fix` ticket, `p0` for SEV1/SEV2), branch, fix
with the failing test now passing, and `land` it. JS-only fixes go out as an OTA
(`ship` skill); API fixes deploy from `main`. If you rolled back in step 2, the fix
re-ships what the rollback removed.

## 5. Postmortem, with its guard

Draft `docs/postmortems/YYYY-MM-DD-<slug>.md` from `docs/postmortems/TEMPLATE.md`,
filled from the timeline you kept. Blameless: the gap in the system, never a person.
The **Guard added** section links the test or check that now fails on this exact
failure, proven against a planted violation; `tests/test_postmortems.py` fails CI
without one. Put the postmortem in the fix's PR, or a follow-up PR when the fix
couldn't wait. Write a memory note (`reflect`) only if the lesson is non-obvious and
will still be true in 30 days.

Reply in under 8 lines: severity, what changed, what you rolled back (or why not),
the cause, the fix PR, and the guard.

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: whether to roll back, flip a kill switch or fix forward (rollback recommended when a release lines up); what users are told and where (in-app, status page, email) for a SEV1 or SEV2; and whether a data exposure needs notifying. Never roll back, flip a flag or message users without a yes.
