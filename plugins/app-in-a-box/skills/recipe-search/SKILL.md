---
name: recipe-search
description: Add search to an App in a Box app with Postgres full-text search (a weighted generated tsvector, a GIN index, and an RLS-safe SECURITY INVOKER function returning keyset pages), plus an optional pgvector hybrid fused by reciprocal rank fusion. Ships the migration, pgTAP isolation tests with a planted negative control, the FastAPI route that queries as the user, and a debounced mobile search screen with analytics. Use when the owner says "search", "find my...", "filter by text", "look up", "semantic search", or the app's list outgrows scrolling.
---

# Recipe: search (Postgres full-text, optional pgvector hybrid)

Search lives in the database the app already has: no second service to run, sync or pay
for. Full-text search handles words, phrases and exclusions; the optional hybrid adds
"close in meaning" matches from embeddings. Both are scoped by the same row-level
security as everything else, so search can never show someone another user's rows.

Everything you copy is in this skill's folder (`$KIT/skills/recipe-search/`, where
`$KIT` is the plugin root): `sql/` for the database, `files/` mirrors the app's layout
(copy as is), `snippets/` are blocks to paste into files the app already has.

⚖️ Owner decisions before starting:
- **What is searchable**: which table, which columns, and which matter most (the
  title-over-body weighting). The recipe uses `items (title, body)`; rename throughout.
- **Language**: `'simple'` (default: no stemming, works for names and any language) or
  one language's config such as `'english'` ("running" finds "run"). One setting, in
  the column and the function.
- **Hybrid or not** (step 5): it needs an embeddings provider, which is a new vendor,
  a cost per row and per search, and user text leaving your stack. Start without it.

## Steps

1. **Migration.** Copy `sql/search.sql` to
   `supabase/migrations/$(date -u +%Y%m%d%H%M%S)_search.sql` and rename `items`,
   `title`, `body`. Step 0 in it creates the example table: delete that block if your
   table exists (and keep its own RLS). What it adds:
   - `search_tsv`, a **generated** `tsvector` (`setweight(... title, 'A') ||
     setweight(... body, 'B')`): it can't drift from the row and needs no trigger.
   - a GIN index on it.
   - `search_items(p_query, p_limit, p_after_rank, p_after_id)`: **SECURITY INVOKER**
     (runs as the caller, so RLS applies) with a pinned `search_path`, an explicit
     `user_id = auth.uid()` filter, `websearch_to_tsquery` (any input is valid; quotes,
     `or` and `-word` work), `ts_rank_cd` ranking, a plain-text `ts_headline` snippet,
     and **keyset pages**: ordered by `(rank desc, id)`, the next page starts after the
     last row's `(rank, id)`. Execute is revoked from `anon` and granted to
     `authenticated`.

   On a **large live table**: adding a stored generated column rewrites the table
   under a lock, and Supabase runs each migration in a transaction, where
   `create index concurrently` is refused. Do it in two passes instead: add a plain
   `search_tsv tsvector` column kept by a `before insert or update` trigger, backfill in
   batches (`update ... where id in (select id ... limit 5000)`), then build the index by
   hand outside a transaction (`create index concurrently if not exists ...`, the line
   is in the migration's comments) and let the migration's `create index if not exists`
   be a no-op.

2. **Database tests.** Copy `sql/search.test.sql` to
   `supabase/tests/database/search.test.sql`, and append `sql/negative_control.sql` to
   `supabase/ci/negative_control.sql`. The tests prove user A never sees user B's rows
   (B owns the best match for every term), anon can't call the function, a call with
   the service key returns nothing, ranking puts title hits first, and the cursor walks
   past ties without repeating a row. The negative control plants the tempting
   rewrite (SECURITY DEFINER, no user filter) and `scripts/db-test.sh` requires the
   suite to go red on it. Run `DATABASE_URL=... scripts/db-test.sh --write-snapshot`:
   the migration changes the schema, so commit the refreshed
   `supabase/schema-snapshot.txt` with it (review its diff first).

3. **Backend.** Copy `files/backend/services/search_service.py`,
   `files/backend/routers/search.py` and `files/tests/test_search.py`. Then:
   - `backend/main.py`: import `search` with the other routers and
     `app.include_router(search.router)`.
   - `backend/config.py` `FEATURE_CONFIG`:
     `"search (Postgres full-text)": ("SUPABASE_URL", "SUPABASE_ANON_KEY"),`
   - `tests/test_wire_contract.py`: import `SearchHit, SearchPage` from
     `backend.routers.search` and add `(SearchPage, "SearchPageWire")` and
     `(SearchHit, "SearchHitWire")` to `RESPONSE_PAIRS`.
   - The `/health` tests that wire everything (`tests/test_health.py`,
     `tests/test_prod_hardening.py`): set `SUPABASE_ANON_KEY` next to `SENTRY_DSN`.
   - `AGENTS.md` → Where things live: a Search row naming the screen, router, service
     and table.
   - Kept the example table? Add `snippets/export.py`'s reader to
     `backend/routers/export.py` and `"items": _read_items` to `EXPORTERS`.

   `GET /api/v1/search?q=&cursor=&limit=` is the one route that queries **as the
   user**: `get_user_db` hands PostgREST the caller's own access token (with the
   publishable key), never the service key. That is what makes RLS apply, and why the
   function's own filter fails closed (no uid, no rows) if someone swaps the client.
   The cursor is opaque base64 of `[rank, id]`; a forged one can only change where
   your own results start. Rate limited at 60 a minute.

4. **Mobile.** Copy `files/mobile/lib/search.ts`, `files/mobile/lib/__tests__/search.test.tsx`,
   `files/mobile/app/(app)/search.tsx`, `files/mobile/__tests__/search-screen.test.tsx`
   and `files/mobile/.maestro/search.yaml`. Paste:
   `snippets/api.ts` at the end of `lib/api.ts` (wire types + adapter),
   `snippets/analytics.ts` into the `analytics` object, `snippets/en.ts` into
   `locales/en.ts` (and every other locale), `snippets/tabs.tsx` into both tab layouts,
   and `snippets/demo.ts` into `lib/demo.ts` so demo mode and the Maestro flow work.
   The pattern:
   - input **debounced** 300 ms, nothing sent under 2 characters;
   - one state at a time: idle hint, skeleton, error with retry and reference,
     **no results** that names the query, results with "Show more" (keyset pages);
   - `search_performed` (results, has_more, duration) and `search_failed`
     (error_code, first or next page). Lengths and counts only, **never the query
     text**: people search for personal things.
   Wire each row's `onPress` to your item's detail route, and set the flow's `appId`
   to the one your other flows in `.maestro/` use.
   Then declare the table and both events in `privacy/data-map.yaml` (the blocks in
   `snippets/data-map.yaml`, renamed to your table) and run
   `python3 scripts/check_data_map.py --write`: CI fails on unmapped columns and props,
   and the store answers and policy draft are regenerated from the map.

5. **Hybrid (optional).** Copy `sql/search_hybrid.sql` (after the search migration)
   and `sql/search_hybrid.test.sql`. It adds `embedding vector(1024)` (match your
   model's size exactly), an HNSW index with cosine distance, and
   `search_items_hybrid(p_query, p_embedding, ...)`: the top 100 of each list, fused by
   **reciprocal rank fusion** (each list adds `1 / (60 + position)`; positions, not
   scores, so text rank and vector distance never need a common scale). Rows without
   an embedding are still found by text; a null query embedding (provider down)
   degrades to plain full-text. Then:
   - the backend embeds the row text on create/edit (a background job, idempotent,
     never inside the request that saves the row) and the query on each search, in
     `backend/services/search_service.py`, and calls `search_items_hybrid` through the
     same `get_user_db` client;
   - register the provider key in `FEATURE_CONFIG` under its own feature, and fall
     back to `search_items` when it's missing;
   - add `postgresql-<ver>-pgvector` next to pgTAP in `.github/workflows/db.yml`;
   - HNSW filters after it searches: with many users and a small `ef_search`, a
     user's nearest rows can fall outside the candidates. On pgvector 0.8+ (Supabase
     has it) add `set hnsw.iterative_scan = relaxed_order` to the function.

## Env / wiring checklist

| Where | What |
|---|---|
| Railway | `railway variables --set "SUPABASE_ANON_KEY=<publishable key>"` (Supabase → Project Settings → API keys). Hybrid: the provider's key too |
| FEATURE_CONFIG | `"search (Postgres full-text)": ("SUPABASE_URL", "SUPABASE_ANON_KEY")`; `/health` lists it until set |
| Supabase | the migration(s); `vector` extension is enabled by the hybrid migration |
| EAS | nothing new: the app calls the API, not Supabase, for search |
| CI (`db.yml`) | hybrid only: install pgvector next to pgTAP |

## Tests to add

Shipped with the recipe, so they arrive green; keep them when you rename:
- pgTAP `search.test.sql`: isolation (the planted definer must fail it), anon refused,
  service key sees nothing, ranking, keyset across ties, websearch syntax, snippet.
- `tests/test_search.py`: 401 without a token, only the caller's rows, the service
  client is never used for the search, no user id reaches the function, keyset
  paging, a forged cursor is a 422, 503 naming the feature without the key.
- `lib/__tests__/search.test.tsx`: debounce (one request per burst, none under 2
  characters), the performed/failed events and their payloads.
- `__tests__/search-screen.test.tsx` (demo mode, real routes): idle, results, no
  results and back; an error with a working retry.
- `.maestro/search.yaml`: the same walk on a simulator.
- Your own: a row created through your app shows up in search; an edited title
  re-ranks (the generated column does it, the test proves it).

## Done means

- [ ] `scripts/db-test.sh` green, and its negative-control step reports the planted
      definer caught.
- [ ] Signed in as two test users on preview builds, each finds only their own rows,
      for a word both of them used.
- [ ] Typing "tom" then "tomato" quickly sends one request (the API's request log or
      the network inspector shows it); a nonsense query shows the no-results state.
- [ ] PostHog shows `search_performed` and, with the API stopped, `search_failed`;
      neither carries the query text.
- [ ] `/health` lists nothing under `features_unavailable` in production.

## When to add a search engine

Postgres covers search over a user's own rows up to millions of rows. Add Typesense or
Meilisearch (a second store kept in sync, with its own scoping to get right) only when
you need typo tolerance as you type, faceted filtering across large shared catalogues,
or search across everyone's public content at scale. ParadeDB's `pg_search` (BM25) is
not available on Supabase, so it isn't an option here.
