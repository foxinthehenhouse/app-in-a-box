// recipe-search: demo mode answers search too. Add the seed to DEMO_SEED's story if you
// like, and this entry to ROUTES in mobile/lib/demo.ts. It mirrors the server's shape
// (SearchPageWire) and its rules: only this user's items, title hits first, and paging
// by an opaque cursor. Matching is a plain substring test, not Postgres' ranking.

const DEMO_ITEMS: { id: string; title: string; body: string }[] = [
  { id: "d0000000-0000-4000-8000-000000000001", title: "Garden plan", body: "Tomatoes along the fence, basil by the door." },
  { id: "d0000000-0000-4000-8000-000000000002", title: "Shopping", body: "Tomato paste, garlic, a new watering can." },
  { id: "d0000000-0000-4000-8000-000000000003", title: "Ideas", body: "Try a herb spiral in the garden this spring." },
];

  // inside ROUTES:
  "GET /api/v1/search": (_body, { query }) => {
    const words = (query.q ?? "").toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length === 0) return { status: 422, body: { detail: "q is required" } };
    const hits = DEMO_ITEMS.filter((i) => words.every((w) => `${i.title} ${i.body}`.toLowerCase().includes(w)))
      .map((i) => ({ hit: i, inTitle: words.some((w) => i.title.toLowerCase().includes(w)) }))
      .sort((a, b) => Number(b.inTitle) - Number(a.inTitle) || a.hit.id.localeCompare(b.hit.id))
      .map(({ hit }) => ({ id: hit.id, title: hit.title, snippet: hit.body }));
    const start = query.cursor ? Number(query.cursor) : 0;
    const page = hits.slice(start, start + 20);
    const next = start + 20 < hits.length ? String(start + 20) : null;
    return { status: 200, body: { items: page, nextCursor: next } };
  },
