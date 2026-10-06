/**
 * Search (recipe-search): debounce what the user types, then page through the
 * server's results with TanStack Query.
 *
 * - The SERVER ranks and decides whose rows (GET /api/v1/search, which runs as the
 *   user so the database's row-level security applies). Nothing here filters or sorts.
 * - Debounced: a request fires once typing pauses for SEARCH_DEBOUNCE_MS, and only
 *   for MIN_QUERY_CHARS or more, so "t", "to", "tom" don't each hit the API.
 * - Keyset paging: `fetchNextPage()` passes the last page's `nextCursor` back.
 * - Analytics: `search_performed` when a first page lands, `search_failed` when one
 *   doesn't. Lengths and counts only: never the query text, which can be personal.
 * - Short-lived: results leave the cache (and with it the offline snapshot) five
 *   minutes after the screen stops using them. They're cheap to refetch, and a
 *   cached list of someone's searches shouldn't outlive the moment.
 */
import { useEffect, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";

import { analytics, startTimer } from "./analytics";
import { ApiError, searchItems, type SearchPage } from "./api";

export const SEARCH_DEBOUNCE_MS = 300;
export const MIN_QUERY_CHARS = 2;
export const searchKey = (q: string) => ["search", q] as const;

/** `value`, once it has stopped changing for `delayMs`. */
export function useDebouncedValue<T>(value: T, delayMs: number = SEARCH_DEBOUNCE_MS): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return settled;
}

/** The query as the server will see it, or "" when it's too short to send. */
export function normaliseQuery(raw: string): string {
  const q = raw.trim().replace(/\s+/g, " ");
  return q.length >= MIN_QUERY_CHARS ? q : "";
}

function errorCode(e: unknown): string {
  return e instanceof ApiError ? (e.status === 0 ? "offline" : `http_${e.status}`) : "unknown";
}

/** Fetch one page, with the success/failure events for a first page. */
export async function fetchSearchPage(q: string, cursor: string | null): Promise<SearchPage> {
  const elapsed = startTimer();
  try {
    const page = await searchItems(q, cursor);
    if (!cursor) {
      analytics.searchPerformed({
        query_length: q.length,
        results: page.items.length,
        has_more: page.nextCursor !== null,
        success: true,
        duration_ms: elapsed(),
      });
    }
    return page;
  } catch (e) {
    analytics.searchFailed({
      query_length: q.length,
      page: cursor ? "next" : "first",
      success: false,
      error_code: errorCode(e),
      duration_ms: elapsed(),
    });
    throw e;
  }
}

/**
 * Debounced, paged search for what's in the box. `query` is the settled, normalised
 * text ("" = nothing to search yet: idle, not "no results").
 */
export function useSearch(input: string) {
  const query = normaliseQuery(useDebouncedValue(input));
  const result = useInfiniteQuery({
    queryKey: searchKey(query),
    queryFn: ({ pageParam }) => fetchSearchPage(query, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.nextCursor,
    enabled: query !== "",
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
  const items = result.data?.pages.flatMap((p) => p.items) ?? [];
  // Still typing (input differs from what was searched) counts as pending, so the
  // screen doesn't flash "no results" for the previous query's empty answer.
  const settling = normaliseQuery(input) !== query;
  return { query, items, settling, ...result };
}
