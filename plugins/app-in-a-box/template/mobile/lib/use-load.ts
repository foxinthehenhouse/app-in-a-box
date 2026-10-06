/**
 * Honest screen states, whatever the data source.
 *
 * `useLoaded(query)` is the BRIDGE from TanStack Query (lib/query.ts) to the
 * `Loaded<T>` shape screens render: `data` stays null until there is data,
 * `loading` means "first load, show a skeleton", `refreshing` means "pull to
 * refresh in flight", `error` is a human message (and `errorRef` the short
 * support reference). It also refetches when the screen regains focus, so a
 * change made in a sheet shows when it closes (a no-op while the data is fresh).
 *
 *   const me = useLoaded(useMe());
 *
 * `useLoad(fn)` is the older, uncached loader, kept for one-off reads that
 * shouldn't be cached or persisted. Prefer a query hook in lib/query.ts: it
 * works offline and dedupes requests across screens.
 */
import { useCallback, useRef, useState } from "react";
import { useFocusEffect } from "expo-router";
import type { UseQueryResult } from "@tanstack/react-query";

import { errorMessage, errorReference } from "./api";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  /** Short support reference for the error (error_id / request id), if any. */
  errorRef: string | null;
  /** First load (show a skeleton). */
  loading: boolean;
  /** A pull-to-refresh is in flight (show the spinner, keep the content). */
  refreshing: boolean;
  reload: () => void;
  refresh: () => void;
}

/** Pure mapping, unit-tested: TanStack's status flags -> the states a screen renders. */
export function loadedState<T>(q: Pick<UseQueryResult<T>, "data" | "error" | "isPending" | "fetchStatus">, refreshing: boolean) {
  return {
    data: q.data ?? null,
    error: q.error ? errorMessage(q.error) : null,
    errorRef: q.error ? errorReference(q.error) : null,
    // Pending + paused (offline, nothing cached) is still "loading", not an error.
    loading: q.isPending && !q.error,
    refreshing,
  };
}

export function useLoaded<T>(q: UseQueryResult<T>): Loaded<T> {
  const [refreshing, setRefreshing] = useState(false);
  const { refetch } = q;
  const first = useRef(true);

  useFocusEffect(
    useCallback(() => {
      if (first.current) {
        first.current = false; // the query already fetched on mount
        return;
      }
      void refetch();
    }, [refetch]),
  );

  const refresh = useCallback(() => {
    setRefreshing(true);
    void refetch().finally(() => setRefreshing(false));
  }, [refetch]);

  const reload = useCallback(() => {
    void refetch();
  }, [refetch]);

  return { ...loadedState(q, refreshing), reload, refresh };
}

/** Uncached load-on-focus. Pass a STABLE function (module-level adapter or useCallback).
 * @public Kept for one-off reads (mobile/AGENTS.md); no template screen needs it yet. */
export function useLoad<T>(load: () => Promise<T>): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const run = useCallback(
    (onDone?: () => void) => {
      let alive = true;
      load()
        .then((d) => {
          if (!alive) return;
          setData(d);
          setError(null);
        })
        .catch((e: unknown) => alive && setError(e ?? new Error("failed")))
        .finally(() => {
          if (!alive) return;
          setLoading(false);
          onDone?.();
        });
      return () => {
        alive = false;
      };
    },
    [load],
  );

  useFocusEffect(run);

  const refresh = useCallback(() => {
    setRefreshing(true);
    run(() => setRefreshing(false));
  }, [run]);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    run();
  }, [run]);

  return {
    data,
    error: error ? errorMessage(error) : null,
    errorRef: error ? errorReference(error) : null,
    loading,
    refreshing,
    reload,
    refresh,
  };
}
