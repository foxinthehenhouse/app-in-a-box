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
  `python3 <kit>/scripts/check_contrast.py design/tokens.json`, then re-render.
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
  `onlineManager` ← NetInfo). Reads are query hooks (`useMe()`); writes are
  `useMutation`s with a `mutationKey`, optimistic `onMutate`, rollback in `onError`,
  success + failure analytics, and a `setMutationDefaults` entry so a paused offline
  edit replays after a restart. `useUpdateMe` is the worked example.
- `lib/use-load.ts`: `useLoaded(query)` bridges a query to honest `loading` / `error` /
  `errorRef` / `refreshing` (plus the older uncached `useLoad(fn)`).
- `lib/session.ts`: `signOut()` / `endSession()`: unregister push, clear the cache, sign out.
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
- `lib/analytics.ts`: the only place events are defined.
- `lib/monitoring.ts`: Sentry (no-op in dev / without DSN).

## Design system rules

- **Theme through hooks.** Read colours from `useTheme()` / `makeStyles`, never from a
  module-level `StyleSheet` with a fixed palette: that silently ignores dark mode.
- **Type through `<Text variant>`.** It applies the font, size, weight, line height and
  the Dynamic Type cap (`maxFontSizeMultiplier` from `type.*.maxScale`). Don't set
  `fontSize` in screens.
- **Motion through `lib/motion.ts`.** No raw `withTiming(v, { duration: 300 })`.
  Every preset honours reduce motion; decorative loops/entrances render static.
  Use Reanimated's `.get()`/`.set()` on shared values (React Compiler-safe).
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
- **Ink ramp for text:** `ink` → `inkDim` → `inkFaint`. All three clear 4.5:1 on every
  surface (the contrast check enforces it). `border` is not a text colour.
- **testID:** `{screen}-{component}-{qualifier}`, e.g. `settings-save-button`.
- **Accessibility:** every interactive element has `accessibilityRole` + a purpose
  label ("Save profile", not "Save button"); 48px targets; announce errors with
  `accessibilityRole="alert"`.
- **Analytics:** every screen under `app/(app)/` calls `analytics.screenViewed(...)`
  on mount. Mutations fire success + failure with `success`, `error_code`,
  `duration_ms` (time it with `startTimer()`, not an inline `Date.now()`). Identify by user id only. Never unmask replay.
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
  (`eas env:create` + `scripts/check-eas-shipping-env.js`). `.env` is dev-only.
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
  device, will sync" instead of spinning.

## Gates

`npm run gates` = `tsc --noEmit` + `eslint` + `check-analytics-coverage` +
`check-eas-shipping-env` + `check-replay-unmask` + `check-hardcoded-strings` + `jest`.
Run it before every push. `jest.setup.ts` holds the shared native-module mocks.
