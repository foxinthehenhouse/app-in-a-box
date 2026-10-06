# Incident runbook

From "something is wrong" to the line of code, using the ids the app already carries.

## The ids

| Id | Where it comes from | Where it appears |
|---|---|---|
| `error_id` | the API's global error handler, per 500 | response body, `ApiError.errorId` in the app, Sentry tag `error_id`, the log line `unhandled error <error_id>` |
| `request_id` | `X-Request-ID` (sent by the client, or generated) | response header + 500 body, every log line `[<request_id>]` (or `"request_id"` in JSON logs), Sentry tag `request_id` |
| trace id | the app's `traceparent` / `sentry-trace` headers: the request id without its dashes | Sentry trace view (sampled requests only, `SENTRY_TRACES_SAMPLE_RATE`, 5% by default) |
| release | git sha (`RAILWAY_GIT_COMMIT_SHA`) / EAS update group | `/health` `version`, Sentry release |

## Triage (first 10 minutes)

1. **Is it live?** `curl -s "$API_URL/health?deep=1"`: `status`, `db`,
   `features_unavailable` (a missing env var shows here by name).
2. **What changed?** Last Railway deploy, last OTA (`eas update:list --branch production`),
   last migration, last flag change. If one lines up with the start, [roll it back](rollback.md)
   now, or turn on the feature's kill switch if it has one (below). The `incident` skill
   walks this page and proposes the rollback first.
3. **How big?** Sentry issue → users affected + trend; PostHog → `api_failed` events by
   path/status.

## From a user report to the code

1. Get the `error_id` (the app can show it on the error screen) or the time.
2. Sentry → search `error_id:<id>` → stack trace, release, `request_id` tag. Events are
   scrubbed: no bodies, no user data, no exception messages, by design.
3. Railway → service logs → search the `request_id` → every log line of that request,
   including the handler's own logs. With `LOG_FORMAT=json`, filter `@request_id:<id>`.
4. Reproduce with a test (filter-honouring fake, see `tests/test_prod_fakes.py`), fix,
   ship (OTA for JS, Railway for the API).

## Common failures

| Symptom | Likely cause | Check |
|---|---|---|
| 503 "`<feature>` not configured" | env var missing in this environment | `/health` `features_unavailable`; set it on Railway |
| Sudden 401s → users signed out | a trailing-slash redirect or a proxy dropping `Authorization` | `redirect_slashes=False` still in `main.py`; exact paths in `mobile/lib/api.ts` |
| 429s | rate limit (per user, per bucket) | `rate_limits` table; raise the limit in the route's `rate_limit(...)` |
| Cron run red with 503 / 401 | `CRON_SECRET` unset / mismatched | Railway variable vs GitHub secret |
| Pushes stop for one user | token pruned (`DeviceNotRegistered`) or moved to another account on the same device | `push_tokens` rows for that user |

## Kill switches

A feature behind a `kill-*` flag (`mobile/lib/flags.ts`, `backend/flags.py`) can be
switched off without a release: turn the flag ON in PostHog and both the app (on its
next flag load) and the API (on its next call) stop using it. If PostHog itself is the
problem, set `FLAG_KILL_<NAME>=1` on Railway (the API redeploys in a minute or two).
Turn it back off once the fix ships. Add a kill switch for anything you'd want to stop
in a hurry: a cron that messages users, a new payment path, a third-party call.

## Severity and comms

- **SEV1** data exposure or everyone broken: roll back now, then tell users in-app /
  status page. Data exposure may be a notifiable breach (GDPR: 72 hours).
- **SEV2** a core flow broken for some: fix forward within a day or roll back.
- **SEV3** degraded, workaround exists: ticket it.

## After

Write a postmortem from [the template](../postmortems/TEMPLATE.md) in
`docs/postmortems/` (what broke, detection time, fix) and add the guard that would
have caught it: a test with a negative control, or a `/health` check. The postmortem
links that guard, and `tests/test_postmortems.py` fails CI if it doesn't. If an SLO
(`docs/slo.yaml`) took a hit, say how much budget the incident used.
