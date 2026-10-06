// recipe-search: append to mobile/lib/api.ts (under "Adapters"). Mirrored field for field
// by `SearchPage` / `SearchHit` in backend/routers/search.py; tests/test_wire_contract.py
// compares them once both pairs are listed there.

/** Mirrors backend/routers/search.py `SearchHit` (camelCase aliases). */
export interface SearchHitWire {
  id: string;
  title: string;
  snippet: string;
}

/** Mirrors backend/routers/search.py `SearchPage`. */
export interface SearchPageWire {
  items: SearchHitWire[];
  nextCursor: string | null;
}

export interface SearchHit {
  id: string;
  title: string;
  snippet: string;
}

export interface SearchPage {
  items: SearchHit[];
  /** Pass back as `cursor` for the next page; null on the last one. */
  nextCursor: string | null;
}

export function toSearchPage(w: SearchPageWire): SearchPage {
  return {
    items: w.items.map((h) => ({ id: h.id, title: h.title, snippet: h.snippet })),
    nextCursor: w.nextCursor ?? null,
  };
}

export async function searchItems(q: string, cursor: string | null = null): Promise<SearchPage> {
  const params = new URLSearchParams({ q });
  if (cursor) params.set("cursor", cursor);
  return toSearchPage(await apiFetch<SearchPageWire>(`/api/v1/search?${params.toString()}`));
}
