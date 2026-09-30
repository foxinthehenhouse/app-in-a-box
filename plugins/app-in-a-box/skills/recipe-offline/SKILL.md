---
name: recipe-offline
description: Make an App in a Box app work offline. Tier 1 (built into the template) is TanStack Query with a persisted cache (reads survive restarts and no signal) plus paused, replayed mutations; this recipe extends it to each new resource (query hooks, optimistic mutations, idempotent creates). Upgrade path is PowerSync (a real local SQLite synced with Supabase) for apps whose core loop must write offline. Use when the owner says "offline", "works on the plane / in the gym", "slow network", "cache", or the core loop happens where signal is bad.
---

# Recipe: offline

Two tiers. Start with tier 1; move to tier 2 only when the core loop must **write**
offline for long stretches and merge cleanly.

| | Tier 1: persisted query cache (default) | Tier 2: PowerSync |
|---|---|---|
| Reads offline | yes (last fetched) | yes (full synced subset) |
| Writes offline | queued, replayed in order on reconnect | local-first, synced |
| Conflicts | last write wins at the API | server-authoritative, per-row |
| Cost | built in | PowerSync service + sync rules + schema mirror |
| Fits | most apps | trackers/loggers used without signal |

## Tier 1 is built in: extend it per feature

The template ships tier 1 in `mobile/lib/query.ts` (TanStack Query + AsyncStorage
persister keyed by app version, `onlineManager` ← NetInfo, `focusManager` ← AppState,
queries `offlineFirst`, mutations `networkMode: "online"` so they PAUSE offline instead
of failing), `PersistQueryClientProvider` + `resumePausedMutations()` in
`app/_layout.tsx`, `<OfflineBanner>`, and `clearUserCache()` on sign-out / account
deletion / user change. `useMe()` + `useUpdateMe()` (optimistic, rollback, analytics)
are the worked example; `mobile/lib/__tests__/query.test.tsx` tests it.

For each new resource:

1. **Reads**: a hook in `lib/query.ts` over a `lib/api.ts` adapter (`queryKeys.x`), and
   `useLoaded(useX())` in the screen. Never a bare `apiFetch` in a component.
2. **Writes**: `useMutation` with a `mutationKeys.x`, optimistic `onMutate`, rollback in
   `onError`, success AND failure analytics, invalidate in `onSettled`, **plus a
   `client.setMutationDefaults(mutationKeys.x, { mutationFn })` line in
   `makeQueryClient()`**: a mutation paused offline is persisted without its function,
   and this is what lets it replay after a restart.
3. **Idempotency**: every offline-capable create sends a client-generated UUID
   (`expo-crypto` `randomUUID()`, as `id` or an `Idempotency-Key` header); the backend
   upserts on `(user_id, id)` so a replay doesn't duplicate. Add the column + unique
   constraint in the migration.
4. **UI**: offline, close the sheet and say "saved on this device, will sync"
   (`app/edit-name.tsx` shows it); never a spinner waiting for a network that isn't there.

## Tier 2 steps (PowerSync), when justified

1. ⚖️ Owner decision (new vendor, cost). PowerSync Cloud → connect Supabase (logical
   replication, `powersync` publication) → sync rules that select **only the user's
   rows** (`bucket_definitions` parameterised by `token_parameters.user_id`).
2. `npx expo install @powersync/react-native @journeyapps/react-native-quick-sqlite`;
   mirror the synced tables in a PowerSync schema; a connector whose `fetchCredentials`
   returns the Supabase session and whose `uploadData` sends queued CRUD to the
   **FastAPI** endpoints (not straight to Supabase: backend computes, rules stay in one place).
3. Screens read with `useQuery` from PowerSync's SQL; writes go to local SQLite.
4. Env: `EXPO_PUBLIC_POWERSYNC_URL` via `eas env:create` (preview + production) and
   `EAS_MANAGED`.

## Env / wiring checklist

| Where | Tier 1 | Tier 2 |
|---|---|---|
| EAS | none (built in) | `EXPO_PUBLIC_POWERSYNC_URL` + `EAS_MANAGED` |
| Railway / FEATURE_CONFIG | none | none (sync service is client ↔ PowerSync) |
| Supabase | idempotency column + unique `(user_id, id)` | replication publication; sync rules reviewed for user scoping |

## Tests to add

- Per new mutation, copy the cases in `lib/__tests__/query.test.tsx`: optimistic value
  then rollback on a 4xx (with the failure event), and offline → paused → replayed once
  after `onlineManager.setOnline(true)`.
- Backend: a replay with the same client id doesn't create a second row (test with the
  filter-honouring fake).
- Maestro (airplane mode on the simulator): open the app offline → last data shows;
  create an item → marked pending; back online → synced.

## Done means

- [ ] Kill the app, enable airplane mode, reopen: the main screens render their last data.
- [ ] Create/edit offline, reconnect: exactly one server row per action, in order.
- [ ] Sign out and in as another user: no trace of the first user's data.
