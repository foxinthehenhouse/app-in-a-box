---
name: scaffold
description: Phase 4 of App in a Box. Generates the app from the interview and design answers. It creates the Expo app, overlays the template (auth, API client, analytics, monitoring, UI primitives, guards), generates tokens, writes the backend and migrations, adapts the core-loop screen and data model to the brief, and makes the first commit. It needs no cloud accounts.
---

# Phase 4: Scaffold

Everything here runs locally. No secrets are needed yet. Read `appbox.yaml` and
`docs/product/BRIEF.md` first.

## 1. Expo app first (versions come from Expo, not from this kit)

Create it **before** `git init`, with stdin closed: in a dogfood run,
`create-expo-app` inside an already-initialised repo wrote every file and then hung
(it waits on a finishing step that never returns). If it still hangs after
`App.tsx` and `package.json` exist, kill it: the project is complete.

```
npx --yes create-expo-app@latest mobile --template blank-typescript --no-install </dev/null
```

The Expo template ships its own `mobile/AGENTS.md` (routes in `src/app/`, which this
kit doesn't use) and `mobile/.claude/settings.json` (enables Expo's official Claude
plugin, but only when an agent starts inside `mobile/`). The renderer replaces the
AGENTS.md with the kit's (which keeps Expo's "read the versioned docs" rule); remove
the nested settings so the repo has ONE harness:

```
rm -rf mobile/.claude
```

```
cd mobile && rm -f App.tsx index.ts && npm install --no-audit --no-fund </dev/null
```

Then install everything the template uses, with one script (it is the single list,
shared with `scripts/demo.sh` and the kit selftest, so they can't drift):

```
"$KIT/scripts/mobile-deps.sh" mobile
```

It runs `npx expo install` (so every version matches the SDK) for: `react-dom` +
`react-native-web` (web target; `react-dom` must be in the FIRST install or npm later
picks a newer React than the SDK pins and every install fails with ERESOLVE),
`expo-router` + `react-native-screens` + `react-native-safe-area-context`,
`react-native-reanimated` 4 + `react-native-worklets` + `react-native-gesture-handler`,
`expo-haptics`, `expo-symbols`, `expo-splash-screen`, `expo-system-ui`, `expo-font`,
`@shopify/flash-list`, Supabase, PostHog, Sentry and friends, plus the v1.0 production
set: TanStack Query + its AsyncStorage persister + NetInfo (offline), `expo-notifications`
(push), `expo-updates` (OTA), `expo-clipboard` / `expo-sharing` / `expo-file-system`
(error references, data export), `react-hook-form` + `zod` (forms), `i18next` +
`react-i18next` + `expo-localization` (i18n); then the dev tools (`eslint-config-expo`,
`jest-expo`, `@testing-library/react-native`). It sets `main`, the `gates` / `lint` /
`typecheck` / `test` / `web` / `demo` / `check-strings` scripts, and jest's `preset`,
the worklets `resolver` (without it any test that imports a component crashes under
Reanimated 4) and `setupFiles` (`jest.setup.ts`: NetInfo + AsyncStorage mocks). If Expo's API is blocked by a proxy it retries with
`EXPO_OFFLINE=1` (the SDK's bundled version map); npm itself still needs the registry.

### What the template gives you (so you build on it, not around it)

- **Native tabs** (`app/(app)/_layout.tsx`, `expo-router/unstable-native-tabs`): Liquid
  Glass on iOS 26, Material 3 on Android, a tab list on web. Icons are SF Symbols
  (`sf`) + Material Symbols (`md`). Keep 2 to 4 tabs.
- **Sheets are routes** (`presentation: "formSheet"`), registered once on the root
  Stack in `app/_layout.tsx`. `app/edit-name.tsx` is the pattern to copy.
- **Light + dark** from `design/tokens.json`, following the OS with a user override
  (Settings → Appearance). A single-palette (v1) token file locks to its mode.
- **Component library** in `components/ui/` and a dev-only `/gallery` of all of it.
- **Demo mode**: `EXPO_PUBLIC_DEMO=1` (in `mobile/.env`, or `npm run demo`) swaps in the
  in-memory fake in `lib/demo.ts`. Use it to click through the app before phase 5.
- **Production capabilities, built in** (each with jest tests; see `mobile/AGENTS.md`):
  account deletion (Settings → Delete account), "Download my data" (`GET
  /api/v1/me/export`, share sheet), request ids on every call with a copyable error
  reference, offline-first data (`lib/query.ts`, optimistic edits that queue offline,
  `OfflineBanner`), the push client (`lib/push.ts`, Settings toggle, no-op until a device
  build with an EAS projectId), deep links through one resolver (`lib/links.ts`,
  `app/+native-intent.tsx`; universal links via `node scripts/set-app-domain.js`), OTA
  updates (`runtimeVersion` fingerprint policy, a channel per eas.json profile,
  `UpdateBanner`), react-hook-form + zod forms (`FormField`), and i18n (every string in
  `locales/en.ts`, `check-hardcoded-strings.js` in the gates, an `en-XA` pseudo-locale
  test). Still recipes: social sign-in, payments, PowerSync, AI features, and the push
  **credentials** (`recipe-push`).

## 2. Repo

```
git init -b main
```

(Skip it if `.git` exists.) Everything in this phase lands in one bootstrap commit on
`main`. That's the only commit ever made on `main` directly.

## 3. Overlay the template

From the repo root, with the values from `appbox.yaml`:

```
python3 "$KIT/scripts/render.py" --target . --name "<name>" --slug <slug> --bundle-id <bundle_id> --owner <owner_handle> --one-liner "<one_liner>" --force
```

`--force` is correct here
because it replaces the create-expo-app defaults (`app.json`, `tsconfig.json`).
The renderer also themes `app.json` from the tokens (splash background per mode,
`userInterfaceStyle`) and draws a placeholder icon, adaptive icon, splash mark and
favicon into `mobile/assets/brand/` (the app's initial in `onAccent` on `accent`).
Drop a real 1024px `design/icon.png` and re-render to use your own.
`design/tokens.json`, `appbox.yaml` and `BRIEF.md` are protected and never
overwritten. The renderer also generates `mobile/lib/tokens.ts` and the
Claude/Codex adapters (`.claude/skills`, `.codex/*`).

## 4. Make it *their* app (the part that needs judgement)

The template is a correct skeleton. Now shape it to the brief:

1. **Data model.** Add one migration per BRIEF table, named
   `supabase/migrations/<UTC timestamp>_<name>.sql`, following
   `.agents/rules/db-migrations.md` (RLS, `user_id` FK, rollback comment). If
   `sensitive_data` includes financial data, money is integer minor units.
2. **Backend.** One router + service per core-loop resource, scoped by `user.id`,
   with `Wire` response models and tests. Copy the pattern in `routers/me.py` and
   `tests/test_me.py`, including the filter-honouring fake.
3. **Mobile.** Replace the empty state in `app/(app)/index.tsx` with the core-loop
   screen, built from `components/ui` (skeleton while loading, `EmptyState`, toast on
   save, `Celebration` on the loop's payoff), with a `*Wire` type + adapter in
   `lib/api.ts`, analytics helpers for the core action (success + failure), and honest
   empty/error states. Add each new endpoint to `ROUTES` in `lib/demo.ts` with seeded
   data from the brief, so demo mode keeps working. Add one `NativeTabs.Trigger` per v1
   screen (keep it to 2–4) and use `FlashList` for any list that can outgrow a screen.
4. **Analytics.** Add the 5 north-star events from the brief as typed helpers, each
   with a real call site.
5. **Domain rules.** For each `sensitive_data` entry, copy
   `.agents/rules/optional/<domain>.md` up to `.agents/rules/` and add a row to the
   path-rules table in `AGENTS.md`.
6. **Draft AGENTS.md from the interview.** It's the file every future agent reads
   first, so write it from the brief, not from memory:
   - `appbox:product`: who it's for, their problem in their words, the core loop,
     the positioning line (BRIEF → Positioning), the north-star metric and the top
     riskiest assumption (VALIDATION.md). At most 10 lines.
   - `appbox:critical-rules` (2–4 domain rules from the brief), `appbox:ai-fence`,
     `appbox:voice`, `appbox:domain-rules`.
   - **Stack line:** drop PostHog / Sentry from it if `stack.analytics` /
     `stack.errors` is `none`, and say "(declined: no-op until enabled)".
   - **`## Where things live`:** one row per core-loop resource you added in steps
     1–3 (its screens, router, service, tables). Keep the template's rows.
   Delete each marker comment once it's filled. Then **show the owner the Product
   section and the map and ask (structured): "Does this describe your app? Anything
   wrong or missing?"** Apply edits before committing. From here on the harness lint
   keeps it honest: `tests/harness/test_agents_md_current.py` fails CI on any
   unfilled marker (once `progress.scaffold` is done) or any screen, router, service
   or table missing from the map, so every feature PR updates it.
7. **AI (only if `ai.enabled`).** Add `backend/services/<name>_service.py` as the
   only module that calls the model API, register `ANTHROPIC_API_KEY` (or the
   provider's key) in `FEATURE_CONFIG`, and state the fence in AGENTS.md rule 8.

## 5. Verify locally

```
scripts/dev-venv.sh python -m pytest -q
```

```
cd mobile && npm run gates
```

Both must be green. Then boot the app with no accounts: `cd mobile && npm run demo`
(or `EXPO_PUBLIC_DEMO=1 npx expo start --web`); any email and any 6-digit code sign
you in. Without demo mode and before phase 5, sign-in renders but sending a code
fails, which is expected. Never put `EXPO_PUBLIC_DEMO` in `eas.json`: the env guard
fails the gates if you do.

## 6. Bootstrap commit

```
git add -A && APPBOX_BOOTSTRAP=1 git commit -m "chore: scaffold <name> with App in a Box"
```

```
git config core.hooksPath .githooks
```

From here on the git hooks refuse commits on `main`, staged `.env` files and
key-shaped strings, and run the gates before every push, whichever agent is
driving. Everything until the first PR is committed on a setup branch:

```
git switch -c chore/appbox-setup
```

Set `progress.scaffold: done` and commit it there.
