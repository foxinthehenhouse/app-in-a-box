# Incident runbook

From "something is wrong" to the line of code, using the ids the app already carries.

## The ids

| Id | Where it comes from | Where it appears |
|---|---|---|
| `error_id` | the API's global error handler, per 500 | response body, `ApiError.errorId` in the app, Sentry tag `error_id`, the log line `unhandled error <error_id>` |
| `request_id` | `X-Request-ID` (sent by the client, or generated) | response header + 500 body, every log line `[<request_id>]` (or `"request_id"` in JSON logs), Sentry tag `request_id` |
| release | git sha (`RAILWAY_GIT_COMMIT_SHA`) / EAS update group | `/health` `version`, Sentry release |

## Triage (first 10 minutes)

1. **Is it live?** `curl -s "$API_URL/health?deep=1"`: `status`, `db`,
   `features_unavailable` (a missing env var shows here by name).
2. **What changed?** Last Railway deploy, last OTA (`eas update:list --branch production`),
   last migration. If one lines up with the start, [roll it back](rollback.md) now.
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

## Severity and comms

- **SEV1** data exposure or everyone broken: roll back now, then tell users in-app /
  status page. Data exposure may be a notifiable breach (GDPR: 72 hours).
- **SEV2** a core flow broken for some: fix forward within a day or roll back.
- **SEV3** degraded, workaround exists: ticket it.

## After

Write a short note (what broke, detection time, fix, the guard that would have caught
it) and add that guard: a test with a negative control, or a `/health` check.
