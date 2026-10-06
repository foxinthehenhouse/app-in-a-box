// recipe-search: add these two entries inside `export const analytics = { ... }` in
// mobile/lib/analytics.ts. lib/search.ts is their call site. Never put the query text
// in an event: people search for personal things. Lengths and counts tell you enough.

  /** A first page of search results landed (zero results is still a success). */
  searchPerformed: (p: { query_length: number; results: number; has_more: boolean; success: true; duration_ms: number }) =>
    capture("search_performed", p),
  /** A search request failed: the failure half of search_performed. */
  searchFailed: (p: { query_length: number; page: "first" | "next"; success: false; error_code: string; duration_ms: number }) =>
    capture("search_failed", p),
