-- Full-text search over the caller's own items (recipe-search).
-- Copy to supabase/migrations/<UTC yyyymmddhhmmss>_search.sql, then rename `items`,
-- `title` and `body` to your table and columns (every occurrence, including the tests).
--
-- What it adds:
--   * items.search_tsv: a GENERATED tsvector, title weighted A over body B, so it can
--     never drift from the row and no trigger has to keep it fresh
--   * a GIN index on it
--   * search_items(): SECURITY INVOKER, so the caller's RLS applies, AND an explicit
--     `user_id = auth.uid()` filter, so a service-role call (no uid) returns nothing
--     rather than everyone's rows. Keyset pages ordered by (rank desc, id asc).
--
-- Rollback:
--   drop function if exists public.search_items(text, integer, real, uuid);
--   drop index if exists public.items_search_idx;
--   alter table public.items drop column if exists search_tsv;
--   drop table if exists public.items;   -- only if this migration created it (step 0)

-- 0. The example table. DELETE this block if your table already exists; keep the rest.
create table if not exists public.items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null check (char_length(title) <= 200),
  body text not null default '' check (char_length(body) <= 20000),
  created_at timestamptz not null default now()
);
create index if not exists items_user_idx on public.items (user_id, created_at desc);
alter table public.items enable row level security;
drop policy if exists "items_select_own" on public.items;
create policy "items_select_own" on public.items
  for select using ((select auth.uid()) = user_id);

-- 1. The search column. 'simple' splits words and lowercases, with no stemming and no
-- stop words: right for names, mixed languages and short text. For one-language prose,
-- use that language's config ('english', 'german', ...) here AND in search_items(), so
-- "running" finds "run". The two-argument to_tsvector is IMMUTABLE, which a generated
-- column requires. Adding a stored generated column rewrites the table under a lock:
-- instant on a new or small table; see the recipe for a big, live one.
alter table public.items
  add column if not exists search_tsv tsvector
  generated always as (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(body, '')), 'B')
  ) stored;

-- 2. The index. Supabase runs each migration in a transaction, where CREATE INDEX
-- CONCURRENTLY is refused, so the migration builds it plainly (fine while the table is
-- small). On a large live table, build it by hand first, outside a transaction:
--   create index concurrently if not exists items_search_idx on public.items using gin (search_tsv);
-- and this line becomes a no-op.
create index if not exists items_search_idx on public.items using gin (search_tsv);

-- 3. The search function. websearch_to_tsquery never raises on user input: quotes make a
-- phrase, `or` an alternative, `-word` an exclusion, and stray punctuation is ignored.
-- The cursor is the last row's (rank, id); pass both or neither. Rank is `real`, the
-- type ts_rank_cd returns, so a rank that went out as JSON compares equal coming back.
create or replace function public.search_items(
  p_query text,
  p_limit integer default 20,
  p_after_rank real default null,
  p_after_id uuid default null
)
returns table (id uuid, title text, snippet text, rank real)
language sql
stable
security invoker
set search_path = ''
as $$
  with q as (
    select websearch_to_tsquery('simple', coalesce(p_query, '')) as tsq
  ),
  page as (
    select i.id, i.title, i.body, ts_rank_cd(i.search_tsv, q.tsq)::real as rank, q.tsq
    from public.items i, q
    where i.user_id = (select auth.uid())   -- belt to RLS's braces; see the header
      and i.search_tsv @@ q.tsq
      and (
        p_after_rank is null or p_after_id is null
        or ts_rank_cd(i.search_tsv, q.tsq)::real < p_after_rank
        or (ts_rank_cd(i.search_tsv, q.tsq)::real = p_after_rank and i.id > p_after_id)
      )
    order by rank desc, i.id
    limit least(greatest(coalesce(p_limit, 20), 1), 50)
  )
  -- ts_headline is the expensive part, so it only runs on the page, not on every match.
  select p.id, p.title,
         ts_headline('simple', p.body, p.tsq, 'MaxWords=24, MinWords=8, StartSel="", StopSel=""'),
         p.rank
  from page p
  order by p.rank desc, p.id
$$;

-- Signed-in users only. Postgres grants EXECUTE to PUBLIC by default; the anon key ships
-- in every app binary and has no uid to search with anyway.
revoke execute on function public.search_items(text, integer, real, uuid) from public, anon;
grant execute on function public.search_items(text, integer, real, uuid) to authenticated;
