---
name: recipe-push
description: Turn on push notifications in an App in a Box app and use them for a feature. The client (mobile/lib/push.ts, a Settings toggle, tap-to-route) and the backend (push_tokens, push_service, receipts cron) are built into the template; this recipe covers the store credentials, asking at the right moment for a feature, send sites, tests and the done-means check. Use when the owner wants reminders, nudges, "notify me when", or push notifications of any kind.
---

# Recipe: push notifications

## Built in (don't rebuild it)

| Piece | Where |
|---|---|
| Token table, atomic register, scoped delete | `push_tokens` + `register_push_token()`; `POST/DELETE /api/v1/me/push-token` |
| Sending, batching, dead-token pruning | `backend/services/push_service.py` (`send_to_user`), `/internal/cron/push-receipts` |
| Client | `mobile/lib/push.ts`: `enablePush()` (asks, gets the Expo token with the EAS projectId, registers), `disablePush()`, re-register on launch, `usePushNavigation()` (taps → `lib/links.ts` `resolveDeepLink`, so a payload can only open a linkable route) |
| Settings toggle | `app/(app)/settings.tsx` → Notifications (`usePushSetting()`), with `pushChanged` success/failure analytics |
| Sign-out / deletion | `lib/session.ts` unregisters before signing out; account deletion cascades server-side |
| No-op where push can't work | web, simulators, Expo Go, and before `eas init` (no projectId): the toggle says "not available", expo-notifications is never loaded |
| Tests | `mobile/lib/__tests__/push.test.ts` (mocked module), `tests/test_prod_push.py` |

## Steps (per feature that sends)

1. **Credentials** (once, owner): see the checklist below. Until then, tokens register
   but Apple/Google refuse delivery.
2. **Ask at the moment of value, never on launch.** Where the feature lives, show one
   line explaining the value ("Get a nudge when your streak is at risk") with Allow /
   Not now; on Allow call `enablePush()` and toast the outcome like Settings does. iOS
   lets you ask once; a cold prompt on first launch burns it.
3. **Make the target linkable**: add its pattern to `LINKABLE_ROUTES` in
   `mobile/lib/links.ts` (e.g. `"/thing/:id"`), or taps land on home.
4. **Send** from a service or job: `push_service.send_to_user(db, user_id, title, body,
   {"url": "/thing/123"})`. Copy follows the Voice section of `AGENTS.md`; no PII in
   the payload (it transits Apple/Google). Marketing pushes need an explicit opt-in.
5. Schedule `/internal/cron/push-receipts` every 30 min (`docs/runbooks/release.md`).

## Env / wiring checklist

| Where | What |
|---|---|
| EAS project | `eas init` writes `expo.extra.eas.projectId` (the client reads it; no env var) |
| iOS credentials | `eas credentials` → iOS → Push Notifications: let EAS create the APNs key |
| Android credentials | Firebase project → `google-services.json` in `mobile/`, `"android": { "googleServicesFile": "./google-services.json" }`; upload the FCM V1 service-account key with `eas credentials` |
| app.json | `"expo-notifications"` plugin already listed (add `icon`/`color` options for Android if you like) |
| Railway | optional `EXPO_ACCESS_TOKEN` only with Expo "enhanced push security"; then add it to `"push (Expo)"` in `FEATURE_CONFIG` |
| Cron | `CRON_SECRET` set (receipts job) |

## Tests to add

- Per send site: a backend test (filter-honouring fake) asserting it sends to the right
  user only, with a `url` that `resolveDeepLink` accepts.
- Per new linkable route: a case in `mobile/lib/__tests__/links.test.ts`.
- If the feature has its own pre-prompt: a jest test that Not now never calls
  `enablePush()`.

## Done means

- [ ] On a physical device (preview build), Settings → Notifications on → a row appears
      in `push_tokens` for your user only.
- [ ] `send_to_user` against production delivers; tapping it opens the `url` screen.
- [ ] Uninstall, send again, run the receipts job 15+ min later: the token row is gone.
- [ ] Signing out removes the token row; signing in as someone else on the same phone
      moves it to them.
