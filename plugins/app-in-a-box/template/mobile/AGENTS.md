# __APP_NAME__: mobile

Auto-loaded under `mobile/` (Claude Code via CLAUDE.md, Codex via AGENTS.md). See `../AGENTS.md`.

**Expo changes every SDK: don't trust memory** (Expo's own advice). Before writing code
against an Expo, EAS or React Native API, read the expo major version in this folder's
package.json and the matching versioned docs (`https://docs.expo.dev/versions/v<major>.0.0/`,
index at `https://docs.expo.dev/llms.txt`). Add native packages with `npx expo install`,
never `npm install`, so versions match the SDK. Routes live in `app/` here (Expo's own
template says src/app; this kit doesn't use it).

## Structure

- `app/`: Expo Router routes. `(auth)/` = signed-out, `(app)/` = signed-in **native
  tabs** (`expo-router/unstable-native-tabs`: SF Symbols via `sf`, Material via `md`).
  `app/_layout.tsx` owns the providers and the auth gate (`Stack.Protected`). Never
  `router.replace` into a group to sign someone in; change auth state and the guard moves them.
- **Sheets are routes** presented as a native `formSheet` (`app/edit-name.tsx` is the
  example), registered ONCE on the root Stack in `app/_layout.tsx`, never inside the
  tabs (registered in both, "back" pops the previous tab instead of closing the sheet).
  Close with `closeSheet()`; always show a Close button.
- `app/gallery.tsx`: dev-only component gallery (Settings → Developer). Add every new
  component there. It renders both colour modes side by side.
- `components/ui/`: the component library, imported from `components/ui` only:
  `Screen` `Card` `Section` · `Text variant=` / `Display` `Title` `Heading` `Body` `Meta`
  `ErrorText` · `Button` `IconButton` `PressableScale` · `Field` · `Chip`
  `SegmentedControl` (native via @expo/ui on iOS / Android) · `ListRow` · `EmptyState`
  `Skeleton` `SkeletonCard` · `Toast` (`useToast`) · `Badge` `Avatar` `ProgressBar`
  `AnimatedNumber` `StatCard` · `Media` (expo-image) · `Toggle` (themed switch) · `Celebration` ·
  `SheetHeader` · `Icon` · `FormField` (Field bound to react-hook-form) · `ErrorNotice`
  (error + copyable support reference + retry) · `OfflineBanner` · `UpdateBanner`.
- `lib/tokens.ts`: **generated** from `../design/tokens.json` (both palettes, type
  roles, motion, elevation, opacity). Never hand-edit it. Change the JSON, run
  `python3 scripts/check_contrast.py design/tokens.json` (repo root; `npm run gates`
  runs it too), then re-render.
- `lib/theme.ts`: `useTheme()` (colours for the current mode, `type`, `space`,
  `radius`, `elevation`…), `makeStyles((t) => ({...}))` for themed StyleSheets,
  `useThemePreference()` for the System/Light/Dark setting.
- `lib/motion.ts`: `animateTo`, `springTo`, `timing`, `spring`, `entrance`,
  `useReducedMotion`, and `haptic.*`.
- `lib/api.ts`: the only backend client. `*Wire` types mirror Pydantic models; adapters
  map wire → UI types. A generic cast is not validation. Every call sends an
  `X-Request-ID`; an `ApiError` carries `requestId` / `errorId`, and
  `errorReference(e)` is the 8-character code `<ErrorNotice reference>` shows.
- `lib/query.ts`: **offline-first data** (TanStack Query + AsyncStorage persister,
  `onlineManager` ← NetInfo). Reads are query hooks (`useMe()`); each write is ONE
  exported option set (`mutationKey`, `scope`, optimistic `onMutate`, rollback in
  `onError`, success + failure analytics) registered with `setMutationDefaults` AND
  spread into its hook, so a paused offline edit replays after a restart with its
  rollback and events intact. `updateMeOptions` / `useUpdateMe` is the worked example.
- `lib/use-load.ts`: `useLoaded(query)` bridges a query to honest `loading` / `error` /
  `errorRef` / `refreshing` (plus the older uncached `useLoad(fn)`).
- `lib/session.ts`: `signOut()` / `endSession()`: unregister push, clear the cache, sign out.
- `lib/supabase.ts` + `lib/secure-store.ts`: the Supabase session is stored in the device
  keychain / keystore via `expo-secure-store`, chunked under its 2048-byte value limit;
  web (no SecureStore) falls back to supabase-js's localStorage. ⚖️ Kyle 2026-10-02:
  expo-secure-store for the session (over AsyncStorage).
- `lib/config.ts`: `configured` / `MISSING_CONFIG`: a build missing its `EXPO_PUBLIC_*`
  server settings says so (`errors.misconfigured` on sign-in and on every call, one
  monitoring report at boot) instead of pretending to be offline.
- `lib/push.ts`: push client (`enablePush()` from a user action, never on launch;
  no-op on web/simulator/Expo Go; taps route through `lib/links.ts`).
- `lib/links.ts`: `resolveDeepLink()`, the ONE mapper from URL/push payload to route
  (`app/+native-intent.tsx` uses it). Add a pattern to `LINKABLE_ROUTES` to make a
  screen linkable. Universal links: `node scripts/set-app-domain.js <domain>`.
- `lib/updates.ts`: OTA (expo-updates, `runtimeVersion` fingerprint policy, channels
  per eas.json profile); `useUpdatePrompt()` drives `<UpdateBanner>`. No-op in dev.
- `lib/forms.ts`: zod schemas; messages are i18n keys. `lib/export.ts`: "Download my data".
- `lib/i18n.ts` + `locales/en.ts`: every user-facing string (see Conventions).
- `lib/demo.ts`: demo mode (`EXPO_PUBLIC_DEMO=1`, dev only). Add a handler to `ROUTES`
  for every new endpoint, or demo mode 404s it.
- `lib/analytics.ts`: the only place events are defined (`lib/analytics-optin.ts` holds
  the Settings opt-in switch, which reads the SDK's flag and orders its capture so it is
  never dropped).
- `lib/monitoring.ts`: Sentry (no-op in dev / without DSN).

## Design system rules

- **Read `../DESIGN.md` before any UI work.** It is the design system in one page
  (palette in both modes, type roles, spacing, radius, motion, component recipes, the
  do's and don'ts), generated from `../design/tokens.json`. Change tokens through the
  design flow, never by hand in DESIGN.md or `lib/tokens.ts`: edit the JSON with the
  owner's yes, run `python3 scripts/design_md.py` (repo root), re-render. CI and
  pre-commit run `python3 scripts/design_md.py --check`.
- **Theme through hooks.** Read colours from `useTheme()` / `makeStyles`, never from a
  module-level `StyleSheet` with a fixed palette: that silently ignores dark mode.
- **Type through `<Text variant>`.** It applies the font, size, weight, line height and
  the Dynamic Type cap (`maxFontSizeMultiplier` from `type.*.maxScale`). Don't set
  `fontSize` in screens.
- **Motion through `lib/motion.ts`.** No raw `withTiming(v, { duration: 300 })`.
  Every preset honours reduce motion; decorative loops/entrances render static.
  Use Reanimated's `.get()`/`.set()` on shared values (React Compiler-safe). **The React
  Compiler is ON** (`experiments.reactCompiler` in app.json, `babel-plugin-react-compiler`
  installed by the kit; ⚖️ Kyle 2026-10-02): keep components pure, no mutation of values
  during render, and let the compiler memoise instead of hand-written `useMemo`.
- **Every tap goes through `PressableScale`** (or a component built on it): press
  scale + tint + a haptic on press-in. Haptic by commitment: `selection` (chips,
  toggles) → `light` (rows, secondary) → `medium` (primary action) → `success`
  (the payoff) / `error`.
- **Object styles for fills.** Never `style={({ pressed }) => ({ backgroundColor })}`:
  function styles that paint a fill get dropped in some Release builds (the button
  turns invisible, and only a Release build shows it).
- **Inputs are controlled.** `Field` never copies `value` into state. Seed a form from
  a fetch with `useState(() => data.value)` AFTER the data loads (skeleton first), or
  the field renders blank over real data and Save writes the blank back.
- **Loading = skeleton, not spinner** (spinners only inside a busy button). Empty =
  `EmptyState` with one next step. Mutation feedback = toast (close a sheet first:
  toasts render under native sheets on iOS). `Celebration` only for the core loop's
  payoff, never routine saves.
- **Lists:** use `@shopify/flash-list` (v2, no size estimates needed) for anything that
  can grow past a screenful.
- **Custom fonts:** every weight of a non-built-in family in `tokens.json` → `font` is
  registered in `lib/fonts.ts` as `<Family>_<weight>` (loaded before the splash hides);
  `lib/__tests__/fonts.test.ts` fails while one is missing, since an unloaded face falls
  back to the system font silently.
- **Device-only bugs:** navigation dismissal and scroll-driven state need one real
  Release-build pass before merge; jest can't see native back resolution or scroll timing.

## Conventions

- **Tokens only.** No hex literals (eslint enforces it), no raw font sizes outside tokens.
- **Ink ramp for text:** `ink` → `inkDim` → `inkFaint`, plus `accent` (ghost buttons,
  links) and `danger` (errors). Every token painted as text clears 4.5:1 on EVERY surface
  (`bg`, `surface`, `surfaceRaised`, `control`); `scripts/check_contrast.py` reads the
  text set from `<Text>`'s tones and `Button`'s inks, so adding a tone makes it checked.
  `success` and `warning` are NOT text: icons, dots, borders (3:1). A success message is
  ink with a glyph, never green text. `border` is not a text colour.
- **testID:** `{screen}-{component}-{qualifier}`, e.g. `settings-save-button`.
- **Accessibility:** every interactive element has `accessibilityRole` + a purpose
  label ("Save profile", not "Save button"); 48px targets; announce errors with
  `accessibilityRole="alert"`.
- **Analytics:** every route under `app/` (layouts and `+*` files excepted) fires an
  `analytics.*` call. Tab screens under `app/(app)/` fire `screenViewed` in
  `useFocusEffect`, never `useEffect`: native tabs mount every tab at launch, so a
  mount-time event logs the other tab on every cold start and never logs a switch (the
  coverage guard fails on it). Sheets and stack routes may use `useEffect`. Mutations
  fire success + failure with `success`, `error_code`, `duration_ms` (time it with
  `startTimer()`, not an inline `Date.now()`). Identify by user id only. Never unmask replay.
- **Honest states.** Loading, empty and error states show the truth. Never render
  placeholder numbers as if they were the user's data.
- **Mutations can't double-fire.** Keep the control disabled until the refetch that
  reflects the change has landed (not just until the request returns), and clear stale
  errors on every successful reload. Otherwise a second tap hits a 409 and logs a false
  failure event.
- **Demo mode** (`EXPO_PUBLIC_DEMO=1` in `mobile/.env`, or `npm run demo`) runs the
  app against the in-memory fake in `lib/demo.ts`. Dev only: it's ANDed with `__DEV__`
  (a release build ignores it), the env guard fails if it appears in `eas.json`
  preview/production, and it must never be `eas env:create`d.
- **Env vars:** any new `process.env.EXPO_PUBLIC_*` must be wired for shipping builds
  (`eas env:create` + `scripts/check-eas-shipping-env.js`). `.env` is dev-only. The
  guard's `EAS_MANAGED` list is a claim until you feed it the store:
  `npx eas-cli env:list --environment preview --format json > /tmp/eas-preview.json`
  then `node scripts/check-eas-shipping-env.js --eas-env /tmp/eas-preview.json`.
- **Copy goes through `t()`.** `const t = useT(); t("settings.title")` in components,
  `i18n.t(...)` only in non-React lib code. Add the key to `locales/en.ts` first (keys are
  typed: a typo fails tsc). Brand names and user data aren't copy. A literal in JSX text,
  a user-facing prop (`label`, `title`, `accessibilityLabel`…) or a `toast.*()` call in
  `app/` or `components/` fails `scripts/check-hardcoded-strings.js`; the rare exception
  ends its line with `// i18n-ignore` and says why. `__tests__/i18n-pseudo.test.tsx`
  renders the screens in the `en-XA` pseudo-locale and fails on any plain-English text:
  add a new screen to it.
- **Forms:** react-hook-form + a zod schema from `lib/forms.ts`, bound with `<FormField>`.
  Keep limits in sync with the backend's Pydantic `max_length`.
- **Offline:** screens read through query hooks, never a bare `apiFetch` in a component.
  Mutations queue offline (`networkMode: "online"` pauses them), so say "saved on this
  device, will sync" instead of spinning. A queued mutation can replay after a restart,
  possibly twice (the request went out, the app died before the response). The profile
  PATCH is idempotent by nature. **A POST that creates something is not**: give it a
  client-generated id (`expo-crypto` `randomUUID()`) in the body, have the backend upsert
  on it, and put `scope: { id: "<resource>" }` on the option set so queued writes to
  one resource run in order. Register its option set with `setMutationDefaults` like
  `updateMeOptions`, or the replay has no rollback and no event.

## Gates

`npm run gates` = `tsc --noEmit` + `eslint` + `check-analytics-coverage` +
`check-eas-shipping-env` + `check-maestro-coverage` + `check-replay-unmask` +
`check-hardcoded-strings` + `check-design-tells` (bounce curves, a Card in a Card,
side-stripe borders, hard shadows, gradient text, emoji as icons: the generic-design
tells in `docs/design/TASTE.md`; a deliberate exception ends its line with
`// design-ignore: <why>`) + `check-test-presence` + the guard self-tests
(`node --test scripts/__tests__/*.test.js`: each guard passes on the template and fails
on a planted violation, so a guard that stops firing fails the gate) +
`check_contrast.py` and `check_design.py` (overused fonts, pure-grey neutrals, the
stock AI violet, overshooting curves) on `design/tokens.json` + `jest --coverage` (a floor over all of
app/, components/ and lib/: raise it as tests land, never lower it to push).
Run it before every push. `jest.setup.ts` holds the shared native-module mocks
(AsyncStorage, NetInfo, SecureStore).

## E2E (Maestro)

Every route has a root testID ending in `-screen` or `-sheet`, and a flow in
`.maestro/` that targets it (`check-maestro-coverage` fails otherwise, and also
fails on a flow `id:` nothing renders). Flows tagged `smoke` run on any build,
including EAS's; `demo` flows sign in through demo mode, so they need a dev build
with `EXPO_PUBLIC_DEMO=1`. Agents drive them through the Maestro MCP
(`list_devices` → `run`, `inspect_screen` when a selector misses). See
`docs/qa/MAESTRO.md`.
