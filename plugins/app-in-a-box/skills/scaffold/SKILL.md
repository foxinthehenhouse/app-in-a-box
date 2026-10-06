---
name: scaffold
description: Phase 4 of App in a Box. Generates the app from the interview and design answers. It creates the Expo app, overlays the template (auth, API client, analytics, monitoring, UI primitives, guards), generates tokens, writes the backend and migrations, adapts the core-loop screen and data model to the brief, and makes the first commit. It needs no cloud accounts. Also use it to re-render the latest template into an existing app (`render.py --force` keeps the brief, tokens and appbox.yaml).
---

# Phase 4: Scaffold

`$KIT` is the plugin root: `${CLAUDE_PLUGIN_ROOT}` in Claude Code, two levels above
this file in Codex, or `<clone>/plugins/app-in-a-box` otherwise.

Everything here runs locally. No secrets are needed yet. Read `appbox.yaml` and
`docs/product/BRIEF.md` first.

## 0. Decisions due now

The scaffold is when the name and the integrations start costing something to change.
Read `design/brief.json` → `decisions` and ask, in one structured round, every
`deferred` entry with `ask_at: scaffold`, which always covers:
- **Name + bundle ID** (interview question 16), unless shape already settled it: the
  working title becomes the name or gets replaced now, because the bundle ID is
  permanent once the app is in a store.
- **Integrations the v1 features imply**, and only those: payments for a paid v1
  feature (`recipe-payments`), reminders that need push credentials (`recipe-push`),
  Apple and Google sign-in (`recipe-social-auth`), an AI feature (`recipe-ai-feature`).
  Say what each one costs and whether it's built now or ticketed for after the scaffold.
- The services and hosting defaults shape stated, in one line ("PostHog, Sentry,
  Railway, GitHub Issues, as assumed; say if not"), not as questions.

Write the answers to `appbox.yaml` (`app.*`, `stack.*`) and flip each entry to `asked`
(or `default` if they kept the assumption).

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
`expo-haptics`, `expo-symbols`, `@expo/ui` (native segmented control), `expo-image`, `expo-splash-screen`, `expo-system-ui`, `expo-font` + `expo-asset` (its loader needs it),
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
- **Component library** in `components/ui/` and a dev-only `/gallery` of all of it. Every
  prototype block has one (SCREENS.md names the exact call): `StatCard`, `Media`
  (expo-image), a native `SegmentedControl` (@expo/ui), `ProgressBar`, `EmptyState`...
  SCREENS.md's Platform and Motion tables say which native piece and which
  `lib/motion.ts` call reproduce each thing the founder clicked.
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
  test). Still recipes: social sign-in, payments, PowerSync, AI features, image uploads
  (`recipe-uploads`), and the push **credentials** (`recipe-push`).

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
`design/tokens.json`, `appbox.yaml`, `BRIEF.md` and the root `README.md` are protected
and never overwritten. The README is rendered once with a small "Built with App in a
Box" badge; it's the owner's to keep or delete. The renderer also generates `mobile/lib/tokens.ts` and the
Claude/Codex adapters (`.claude/skills`, `.codex/*`).

## 4. Make it *their* app (the part that needs judgement)

The template is a correct skeleton. Now shape it to the brief **and to the frozen
prototype**: `docs/product/SCREENS.md` (from phase 2) lists every v1 screen, the layout
the founder chose, which kit component each block maps to, the navigation and the
states. Build those screens, in that layout, with those words (the chosen tone's copy
goes into `locales/en.ts`). If a block has no kit component, compose it from
`components/ui` rather than inventing a new style. The founder already approved this;
the app should feel like the prototype they clicked, not a reinterpretation of it.
Features marked out of v1 in SCREENS.md stay out. **No SCREENS.md** (a project that
finished design before the prototype existed): run phase 2's freeze if
`design/prototype.json` exists; otherwise build from BRIEF.md → "Screens (v1)" and say
once that re-running the prototype phase would let them click it first.

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
   data from the brief, so demo mode keeps working. Add one `NativeTabs.Trigger` per tab
   in SCREENS.md → Navigation, and the matching `TabTrigger` in `app/(app)/_layout.web.tsx`
   (web's bottom bar: keep the two in step). Every other screen is a pushed route, every sheet a
   formSheet route. Take each icon's `sf` / `md` names from SCREENS.md → Icons, and use
   `FlashList` for any list that can outgrow a screen.
   **Fonts:** for each family in `design/tokens.json` → `font` that isn't built in,
   install its `@expo-google-fonts/*` package and register every weight the type roles
   use as `<Family>_<weight>` in `lib/fonts.ts` (the file's header shows how). An
   unloaded face silently falls back to the system font, so
   `lib/__tests__/fonts.test.ts` fails, naming the missing keys, until they're all there.
4. **Analytics.** Add the 5 north-star events from the brief as typed helpers, each
   with a real call site.
5. **Domain rules.** For each `sensitive_data` entry, copy
   `.agents/rules/optional/<domain>.md` up to `.agents/rules/` and add a row to the
   path-rules table in `AGENTS.md`.
6. **Draft AGENTS.md from the brief.** It's the file every future agent reads
   first, so write it from `BRIEF.md`, `SCREENS.md` and `VALIDATION.md`, not from memory:
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
   Then let that one module through the import-linter fence: in `pyproject.toml`'s
   forbidden contract set `ignore_imports = ["backend.services.<name>_service -> anthropic"]`
   (`lint-imports` fails any other module that imports the SDK).

### Match check (the prototype is the spec; prove the app matches it)

The founder approved a prototype, not a description of one. Before the bootstrap
commit, check the built app against `docs/product/SCREENS.md` screen by screen:

1. Run `cd mobile && npm run demo` and open every screen SCREENS.md lists (tabs,
   pushed routes, sheets).
2. For each screen, confirm: the same blocks in the same order as its chosen layout;
   the chosen tone's copy, word for word, from `locales/en.ts`; exactly one primary
   action; the empty state SCREENS.md gives it; icons by the `sf` / `md` names in its
   Icons table; features marked out of v1 absent.
3. Hand `design-critic` (`$KIT/agents/design-critic.md`; in Codex do its job inline)
   the screenshots or the rendered component tree of each screen together with
   SCREENS.md, once. It returns PASS or FAIL with at most 7 fixes.
4. Fix every item before the bootstrap commit. Don't commit a FAIL and "fix it in
   phase 8": the scaffold is the one moment the whole app is in view at once.
5. List the screens you checked in the bootstrap commit body (`Match check: home,
   add-item (sheet), history, settings`), so the record says what was verified.

No `npm run demo` (web target broken on this machine)? Say so, check against the
component tree and the test renders instead, and name that in the commit body.

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

Turn the hooks on **first**, so the pre-commit's `.env` and secret-key checks see the
biggest commit this repo will ever get. `APPBOX_BOOTSTRAP=1` only lifts the
"no commits on `main`" rule for this one commit; the other checks still run.

```
git config core.hooksPath .githooks
```

```
git add -A && APPBOX_BOOTSTRAP=1 git commit -m "chore: scaffold <name> with App in a Box"
```

If the hook refuses the commit, it found a staged `.env` or a key-shaped string: fix
that (unstage, move the value to `.env`), never bypass the hook. From here
on the git hooks refuse commits on `main`, staged `.env` files and key-shaped
strings, and run the gates before every push, whichever agent is driving. Everything
until the first PR is committed on a setup branch:

```
git switch -c chore/appbox-setup
```

Set `progress.scaffold: done` and commit it there.
