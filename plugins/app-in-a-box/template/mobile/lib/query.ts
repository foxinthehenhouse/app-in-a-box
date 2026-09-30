/**
 * Offline-first data: TanStack Query with a persisted cache.
 *
 * - Reads come from the cache first (`networkMode: "offlineFirst"`), so the last
 *   data shows with no signal and after a restart (AsyncStorage persister).
 * - The persisted cache is keyed by app version (`buster`): a new build never
 *   reads an old cache shape.
 * - The persisted cache is stamped with its OWNER (the signed-in user id). On
 *   restore it is dropped unless the restored session is that same user: a
 *   session that lapsed while the app was closed must not show A's data to B.
 * - `onlineManager` follows NetInfo; `focusManager` follows AppState. Offline,
 *   queries pause (no error spam) and mutations queue; they replay on reconnect,
 *   and paused mutations survive a restart (`setMutationDefaults` below +
 *   `resumePausedMutations()` after restore in app/_layout.tsx).
 * - `clearUserCache()` on sign-out and account deletion: user B must never see
 *   user A's cache.
 *
 * Every read is a hook here over a lib/api.ts adapter (so the cache holds UI
 * types). Every write is a `useMutation` with a `mutationKey`, an optimistic
 * update in `onMutate`, a rollback in `onError`, and an invalidate in
 * `onSettled`. `useUpdateMe` is the worked example.
 */
import { useSyncExternalStore } from "react";
import { AppState, type AppStateStatus } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import NetInfo from "@react-native-community/netinfo";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { QueryClient, focusManager, onlineManager, useMutation, useQuery } from "@tanstack/react-query";
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client";
import Constants from "expo-constants";

import { analytics, startTimer } from "./analytics";
import { ApiError, getMe, updateMe, type Profile, type ProfilePatch } from "./api";
import { currentUserId } from "./supabase";

export const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;
/** A new app version drops the old persisted cache (its shape may have changed). */
export const CACHE_BUSTER = Constants.expoConfig?.version ?? "0";

export const queryKeys = {
  me: ["me"] as const,
};

export const mutationKeys = {
  updateMe: ["me", "update"] as const,
};

/** Don't retry what retrying can't fix (4xx), and never loop on a signed-out 401. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

export function makeQueryClient(): QueryClient {
  // Under jest, no GC timers (24h for queries, 5 min for mutations): they'd keep
  // the test process alive after the last test.
  const testing = process.env.NODE_ENV === "test";
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        networkMode: "offlineFirst",
        gcTime: testing ? Infinity : CACHE_MAX_AGE_MS, // >= the persister's maxAge, or restored data is GC'd
        staleTime: 30_000,
        retry: shouldRetry,
      },
      // "online", NOT "offlineFirst": offlineFirst fires the request once even with no
      // network, so an offline edit fails, rolls back and logs a false failure instead
      // of queuing. "online" pauses it (onMutate's optimistic update still applies)
      // and resumes it when onlineManager says we're back.
      mutations: { networkMode: "online", retry: 0, ...(testing ? { gcTime: Infinity } : null) },
    },
  });
  // A mutation paused offline is persisted WITHOUT its function; this default is
  // what lets it run again after a restart.
  client.setMutationDefaults(mutationKeys.updateMe, { mutationFn: (patch: ProfilePatch) => updateMe(patch) });
  return client;
}

export const queryClient = makeQueryClient();

const storagePersister = createAsyncStoragePersister({
  storage: AsyncStorage,
  key: "app-query-cache",
  throttleTime: 1000,
});

/** What's on disk: the cache plus whose it is. */
interface OwnedPersistedClient extends PersistedClient {
  owner?: string | null;
}

/**
 * The AsyncStorage persister, owner-aware. Writes stamp the current cache owner
 * (set by lib/auth.tsx); a restore returns the cache only when the session being
 * restored is that same user, and otherwise deletes it before anything renders.
 * A cache with no owner (written signed out, or by an older build) is dropped.
 */
export const persister: Persister = {
  persistClient: (client) => {
    const owned: OwnedPersistedClient = { ...client, owner: cacheOwner };
    return storagePersister.persistClient(owned);
  },
  restoreClient: async () => {
    const saved = (await storagePersister.restoreClient()) as OwnedPersistedClient | undefined;
    if (!saved) return undefined;
    const userId = await currentUserId();
    if (!saved.owner || saved.owner !== userId) {
      await storagePersister.removeClient();
      return undefined;
    }
    setCacheOwner(userId); // the restored data is this user's, even if auth hasn't reported yet
    return saved;
  },
  removeClient: () => storagePersister.removeClient(),
};

export const persistOptions = { persister, maxAge: CACHE_MAX_AGE_MS, buster: CACHE_BUSTER };

/** Sign-out / account deletion: forget everything this user had cached. */
export async function clearUserCache(client: QueryClient = queryClient): Promise<void> {
  client.getMutationCache().clear();
  client.clear();
  try {
    await persister.removeClient();
  } catch {
    // storage unavailable: the in-memory clear above is what matters this session
  }
}

let cacheOwner: string | null = null;

/**
 * Who the in-memory cache belongs to. lib/auth.tsx calls this on every auth
 * change, synchronously, BEFORE the new state renders. A real user change
 * (A -> B, A -> signed out) clears the cache right here, before any of the new
 * user's screens subscribe; signed out -> B clears nothing (there's nothing of
 * anyone's to clear, and clearing then would cancel B's first fetch).
 * Returns true when it cleared.
 */
export function setCacheOwner(userId: string | null, client: QueryClient = queryClient): boolean {
  const changed = cacheOwner !== null && cacheOwner !== userId;
  cacheOwner = userId;
  if (changed) void clearUserCache(client);
  return changed;
}

export function currentCacheOwner(): string | null {
  return cacheOwner;
}

// ---- Connectivity + focus --------------------------------------------------

/** NetInfo -> onlineManager. `isInternetReachable === null` means "not known yet": treat as online. */
export function isOnlineState(state: { isConnected: boolean | null; isInternetReachable?: boolean | null }): boolean {
  return state.isConnected !== false && state.isInternetReachable !== false;
}

let wired = false;
/** Call once at startup (app/_layout.tsx). Safe to call again. */
export function wireConnectivity(): void {
  if (wired) return;
  wired = true;
  onlineManager.setEventListener((setOnline) =>
    NetInfo.addEventListener((state) => setOnline(isOnlineState(state))),
  );
  focusManager.setEventListener((handleFocus) => {
    const sub = AppState.addEventListener("change", (s: AppStateStatus) => handleFocus(s === "active"));
    return () => sub.remove();
  });
}

/** Live online/offline state for UI (the offline banner, "will sync" copy). */
export function useOnline(): boolean {
  return useSyncExternalStore(
    (cb) => onlineManager.subscribe(cb),
    () => onlineManager.isOnline(),
    () => true,
  );
}

// ---- Reads -------------------------------------------------------------------

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: getMe });
}

// ---- Writes ------------------------------------------------------------------

interface UpdateMeContext {
  previous: Profile | undefined;
  elapsed: () => number;
}

/**
 * Optimistic profile edit: the new name shows everywhere immediately, rolls back
 * if the server says no, and refetches either way. Offline, it queues and
 * replays on reconnect (even after a restart). Fires success AND failure analytics.
 */
export function useUpdateMe() {
  return useMutation<Profile, unknown, ProfilePatch, UpdateMeContext>({
    mutationKey: mutationKeys.updateMe,
    mutationFn: (patch) => updateMe(patch),
    onMutate: async (patch, ctx) => {
      await ctx.client.cancelQueries({ queryKey: queryKeys.me });
      const previous = ctx.client.getQueryData<Profile>(queryKeys.me);
      if (previous) ctx.client.setQueryData<Profile>(queryKeys.me, { ...previous, ...patch });
      return { previous, elapsed: startTimer() };
    },
    onError: (error, _patch, context, ctx) => {
      if (context?.previous) ctx.client.setQueryData(queryKeys.me, context.previous);
      analytics.profileUpdated({
        success: false,
        error_code: error instanceof ApiError ? `http_${error.status}` : "save_failed",
        duration_ms: context?.elapsed() ?? 0,
      });
    },
    onSuccess: (saved, _patch, context, ctx) => {
      ctx.client.setQueryData(queryKeys.me, saved);
      analytics.profileUpdated({ success: true, error_code: null, duration_ms: context?.elapsed() ?? 0 });
    },
    onSettled: (_d, _e, _v, _c, ctx) => ctx.client.invalidateQueries({ queryKey: queryKeys.me }),
  });
}
