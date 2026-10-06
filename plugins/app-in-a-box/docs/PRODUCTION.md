# Production readiness checklist

What an App in a Box app needs before real users, and where the kit already covers
it. **Kit** = in the rendered template with a test; **Recipe** = one skill away;
**Owner** = a console/account step no agent can do; **Gap** = not covered yet, do it
yourself. Paths are relative to the rendered app unless they start with `$KIT`.

Run through it before the first TestFlight/Play build, and again before public launch.

## Security

| Item | Status | Where |
|---|---|---|
| Every query scoped by the caller's user id (service key bypasses RLS) | Kit | `backend/AGENTS.md`; filter-honouring fakes in `tests/test_me.py`, `tests/test_prod_fakes.py`; selftest negative controls |
| RLS on every table; service-only tables revoke anon/authenticated | Kit | `tests/test_prod_migrations.py::test_every_table_enables_rls` |
| Multi-row writes atomic (Postgres functions, `security definer`, `search_path=''`, service-role only) | Kit | `db.rpc()`, `register_push_token` example, static tests in `test_prod_migrations.py` |
| Rate limiting on write endpoints, shared across workers | Kit | `backend/ratelimit.py` + `rate_limits` table; `test_rate_limit_holds_across_workers` |
| No in-process state (multi-worker) | Kit | `test_backend_keeps_no_in_process_state` |
| No trailing-slash redirects (RN drops auth on 307) | Kit | `redirect_slashes=False`; `test_trailing_slash_is_not_redirected` |
| Security headers, HSTS in production, no-store on `/api` | Kit | `backend/middleware.py`; `test_security_headers_on_every_response` |
| CORS closed by default (mobile needs none), opt-in via `CORS_ORIGINS` | Kit | `config.cors_origins()` |
| API docs hidden in production | Kit | `test_production_adds_hsts_and_hides_docs` |
| Cron endpoints behind a constant-time shared secret, fail closed | Kit | `routers/internal.py`; `tests/test_prod_cron.py` |
| Dependencies pinned with upper bounds | Kit | `requirements.txt`; `test_every_requirement_has_an_upper_bound` |
| Secrets never in git | Kit | `.githooks/pre-commit` scan; `.env` gitignored |
| Secret rotation procedure | Kit | `docs/runbooks/secrets-rotation.md` |
| Supabase security advisors clean | Owner | Supabase → Advisors → Security, before launch and monthly |
| **Sign-in email through custom SMTP** (Supabase's built-in mailer allows a couple of emails an hour; real users can't sign in without this) | Kit + Owner (domain, key) | provision step 2.7 (`$KIT/scripts/supabase_smtp.py`, Resend recommended: free for 100/day); production `/health` names "email sign-in (custom SMTP)" until `AUTH_SMTP_HOST` is set (`PRODUCTION_FEATURE_CONFIG`, `tests/test_health.py`) |
| Auth hardening: email confirmations, leaked-password protection, OTP expiry, CAPTCHA on sign-up if abused | Owner | Supabase → Authentication settings |

## Privacy and store compliance

| Item | Status | Where |
|---|---|---|
| **Account deletion in-app** (App Store 5.1.1(v), Play data deletion policy) | Kit + Owner (web URL) | `DELETE /api/v1/me` + `tests/test_prod_account_deletion.py`; Settings → Delete account (`mobile/app/delete-account.tsx`: type DELETE → API → sign out → toast; `__tests__/delete-account.test.tsx`). Play also needs a **web** deletion URL (a simple form or email address is accepted): Owner |
| New user tables cascade on account deletion | Kit (rule) | `user_id ... references auth.users on delete cascade` (db-migrations rule); Storage objects need `_delete_user_files()` |
| Data export (GDPR Art. 15/20) | Kit | `GET /api/v1/me/export` (`backend/routers/export.py`: one scoped reader per user-owned table, rate-limited 5/h); `tests/test_v1_export.py` fails if another user's rows leak or a migration adds an `auth.users`-keyed table the export misses. Settings → Download my data writes the JSON and opens the share sheet (`mobile/lib/export.ts`) |
| iOS privacy manifest (`PrivacyInfo.xcprivacy`) | Owner/Gap | Expo generates it from `ios.privacyManifests` in `app.json`; declare required-reason APIs used by your deps (e.g. `UserDefaults` CA92.1, file timestamp C617.1) and collected data types. Check the build warnings Apple emails you |
| App Store privacy "nutrition label" | Owner | Declare: email/user id (auth), crash data (Sentry), product interaction (PostHog), plus anything your features add (push token = device id; purchases; user content sent to an AI provider) |
| Play Data safety form | Owner | Same inventory as above; mark data encrypted in transit and deletable |
| Privacy policy + terms URLs | Owner | Required by both stores and by Sign in with Apple |
| Tracking / ATT | Kit (no tracking) | PostHog is first-party analytics; don't add ad SDKs without ATT |
| Sentry holds no user data | Kit | `observability.scrub_event` strips bodies, users, messages, values |
| Session replay masked | Kit (mobile) | see the mobile analytics rules |

## Reliability and operations

| Item | Status | Where |
|---|---|---|
| Health check with version and optional deep DB ping | Kit | `/health`, `/health?deep=1` |
| Env-gated features visible, never silent | Kit | `FEATURE_CONFIG` / `PRODUCTION_FEATURE_CONFIG` / `OPTIONAL_FEATURE_CONFIG` → `/health` |
| Error monitoring with a user-visible `error_id` | Kit | global handler + Sentry tag |
| Request ids across client, logs and Sentry; JSON logs | Kit | `X-Request-ID` on every call from `mobile/lib/api.ts`, echoed + logged + Sentry-tagged by the API; error UI shows a copyable 8-character reference (`<ErrorNotice>`); `LOG_FORMAT=json`; a 15s request timeout that fails as offline (Retry) |
| Zero-downtime deploys + graceful shutdown | Kit | `railway.json` overlap/draining + uvicorn graceful timeout |
| Scheduled jobs, idempotent | Kit | `/internal/cron/*`, `job_runs`; schedule per `docs/runbooks/release.md` |
| Push notifications (backend) | Kit | `push_service.py`, receipts cron |
| Push notifications (client) | Kit + Owner (credentials) | `mobile/lib/push.ts` + Settings toggle (contextual ask, register/unregister, tap → route); APNs/FCM credentials per `recipe-push` |
| Offline: cached reads, queued writes | Kit | `mobile/lib/query.ts` (persisted TanStack Query, mutations pause offline and replay), `OfflineBanner`; PowerSync tier via `recipe-offline` |
| **Nightly encrypted backups + a restore drill** | Kit + Owner (bucket, key) | `.github/workflows/backup.yml` runs `scripts/backup-db.sh` (`supabase db dump`, age-encrypted to the owner's public key, to R2/S3), on once provision step 8.2 sets `BACKUP_AGE_RECIPIENT`; `tests/test_backup.py` fails if it could print a secret. Monthly `scripts/restore-drill.sh` per `docs/runbooks/backup-restore.md`. Supabase's free plan keeps none; Pro keeps 7 days; add **PITR** for anything with money or irreplaceable user content |
| Free-tier pause | Kit | keep-alive workflow + `keep_alive` table |
| **Uptime alert** | Kit + Owner (account) | provision step 8.1 (`$KIT/scripts/uptime_monitor.py`): Better Stack (recommended, free) watches `/health?deep=1` for `"status":"ok"`, so down and degraded both alert; Sentry Uptime watches `/health` every minute for down. `tests/test_health.py` pins the keyword |
| **Spend caps and billing alerts** | Owner | the checklist in the app's `COST.md` (provision step 8.3): Railway hard limit, Supabase spend cap, Anthropic monthly limit, Sentry/PostHog budgets, one inbox for billing mail |
| Alert routing / on-call | Owner | Sentry alert rule: new issue in production + error spike → email/Slack/phone; one named person on call per week, even if it's you |
| Runbooks | Kit | `docs/runbooks/release.md`, `rollback.md`, `incident.md`, `secrets-rotation.md`, `backup-restore.md` |

## Release pipeline

| Item | Status | Where |
|---|---|---|
| PR previews (OTA when native unchanged, else build) | Kit (unverified schema) | `mobile/.eas/workflows/pr-preview.yml` |
| Production build + submit, or OTA | Kit (unverified schema) | `mobile/.eas/workflows/release.yml` |
| Staged OTA rollout, promoted on crash-free sessions | Kit (unverified schema) | `release.yml` publishes to 10%, then an approval + `update-rollout` to 100%; the gate is in `docs/runbooks/release.md`, and `scripts/rollback-ota.sh` reverts a rollout in progress |
| Readable OTA crashes | Kit | every `type: update` job sets `upload_sentry_sourcemaps: true`; `mobile/lib/monitoring.ts` names each update as its own Sentry release and tags the update id |
| OTA updates in the app | Kit | `expo-updates`, `runtimeVersion: { policy: "fingerprint" }`, a channel per eas.json profile, `UpdateBanner` offers a restart when a fix has downloaded (`mobile/lib/updates.ts`); `eas update:configure` (provision) writes `updates.url` |
| OTA rollback, backend redeploy, migration rollback | Kit | `docs/runbooks/rollback.md` |
| Deep links / universal links | Kit + Owner (domain) | custom scheme works out of the box through `mobile/lib/links.ts` + `app/+native-intent.tsx`; universal/app links: `node scripts/set-app-domain.js <domain> --team-id … --sha256 …`, then host the two `.well-known` files it prints and rebuild |
| Store credentials (ASC API key, Play service account) | Owner | `eas credentials` |

## Capabilities: built in vs recipe

| Capability | Status | Where |
|---|---|---|
| Account deletion, data export, request ids + error reference | Built in | see above |
| Offline-first data (persisted cache, optimistic + queued writes) | Built in | `mobile/lib/query.ts`; PowerSync upgrade: `recipe-offline` |
| Push client + Settings toggle | Built in | `mobile/lib/push.ts`; credentials + send sites: `recipe-push` |
| Deep links | Built in | `mobile/lib/links.ts`; universal links need your domain |
| OTA updates + update prompt | Built in | `mobile/lib/updates.ts` |
| Forms (react-hook-form + zod) | Built in | `mobile/lib/forms.ts`, `FormField` |
| i18n (English + pseudo-locale, hardcoded-string gate) | Built in | `mobile/lib/i18n.ts`, `locales/en.ts`; add a language by copying `en.ts` |
| Apple + Google sign-in | Recipe | `recipe-social-auth` |
| Subscriptions / IAP with server-side entitlements | Recipe | `recipe-payments` |
| AI feature (fenced, capped, evaluated) | Recipe | `recipe-ai-feature` |

## Store review gotchas

- **Demo account**: give App Review a working login (email OTP needs a reviewer path:
  a test account with a fixed code, or a password account for review only).
- **Sign in with Apple** is mandatory on iOS if any other social login is offered.
- **Account deletion** must be findable in the app, not just "email us".
- **Purchases**: digital goods only through IAP; include Restore Purchases; no links to
  external payment (outside allowed storefront programs).
- **Push**: don't require notification permission to use the app; don't send
  marketing pushes without opt-in.
- **Permissions strings**: every `NS*UsageDescription` must say why, specifically.
- **Minimum functionality**: a thin wrapper around a website gets rejected (4.2).
- **Health/finance claims** need care: no medical claims without clearance.
- **Android target SDK** must meet Play's current floor (Expo SDK upgrades handle it:
  stay within a year of the latest SDK).
- **Metadata**: screenshots must show the real app; no placeholder text in the build.
