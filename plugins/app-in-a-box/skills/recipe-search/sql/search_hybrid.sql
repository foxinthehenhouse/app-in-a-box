-- Hybrid search (OPTIONAL, recipe-search): meaning-based matches from pgvector, fused
-- with the full-text ranking by reciprocal rank fusion (RRF). Needs search.sql first.
-- Copy to supabase/migrations/<UTC yyyymmddhhmmss>_search_hybrid.sql.
--
-- 1024 below is the embedding size of the model the backend uses; change every
-- `vector(1024)` to match yours (it has to be exact, and at most 2000 for an HNSW index).
-- The backend writes items.embedding when a row is created or edited, and embeds the
-- query text for each search. Rows with no embedding yet are still found by text.
--
-- Rollback:
--   drop function if exists public.search_items_hybrid(text, extensions.vector, integer, integer, integer);
--   drop index if exists public.items_embedding_idx;
--   alter table public.items drop column if exists embedding;

create schema if not exists extensions;   -- Supabase has it already; plain Postgres (CI) may not
create extension if not exists vector with schema extensions;

alter table public.items add column if not exists embedding extensions.vector(1024);

-- HNSW: good recall with no training step, and it stays good as rows are added. Cosine
-- distance (<=>) suits the normalised embeddings most providers return. Same advice as
-- the GIN index on a large live table: build it CONCURRENTLY by hand first.
create index if not exists items_embedding_idx
  on public.items using hnsw (embedding extensions.vector_cosine_ops);

-- RRF: each list contributes 1 / (k + position) for every row it ranks, and the sums
-- decide the order. Positions, not raw scores, so ts_rank and cosine distance never have
-- to be put on one scale; k = 60 is the usual constant (higher flattens the top ranks).
-- Each side takes its best p_candidates rows; this returns the first p_limit of the
-- fused list (one page: ask for more candidates, not a cursor, if you need depth).
create or replace function public.search_items_hybrid(
  p_query text,
  p_embedding extensions.vector(1024),
  p_limit integer default 20,
  p_rrf_k integer default 60,
  p_candidates integer default 100
)
returns table (id uuid, title text, snippet text, score double precision)
language sql
stable
security invoker
set search_path = ''
as $$
  with q as (
    select websearch_to_tsquery('simple', coalesce(p_query, '')) as tsq
  ),
  fts as (
    select f.id, row_number() over (order by f.rank desc, f.id) as pos
    from (
      select i.id, ts_rank_cd(i.search_tsv, q.tsq) as rank
      from public.items i, q
      where i.user_id = (select auth.uid())
        and i.search_tsv @@ q.tsq
      order by rank desc, i.id
      limit least(greatest(coalesce(p_candidates, 100), 1), 500)
    ) f
  ),
  vec as (
    -- ORDER BY <distance> LIMIT n directly on the table is what lets the HNSW index serve it.
    select v.id, row_number() over (order by v.dist, v.id) as pos
    from (
      select i.id, i.embedding operator(extensions.<=>) p_embedding as dist
      from public.items i
      where i.user_id = (select auth.uid())
        and p_embedding is not null
        and i.embedding is not null
      order by dist
      limit least(greatest(coalesce(p_candidates, 100), 1), 500)
    ) v
  ),
  fused as (
    select coalesce(fts.id, vec.id) as id,
           coalesce(1.0 / (greatest(coalesce(p_rrf_k, 60), 1) + fts.pos), 0)
           + coalesce(1.0 / (greatest(coalesce(p_rrf_k, 60), 1) + vec.pos), 0) as score
    from fts full join vec on fts.id = vec.id
    order by score desc, id
    limit least(greatest(coalesce(p_limit, 20), 1), 50)
  )
  select i.id, i.title,
         ts_headline('simple', i.body, q.tsq, 'MaxWords=24, MinWords=8, StartSel="", StopSel=""'),
         fused.score::double precision
  from fused
  join public.items i on i.id = fused.id
  cross join q
  order by fused.score desc, i.id
$$;

revoke execute on function public.search_items_hybrid(text, extensions.vector, integer, integer, integer) from public, anon;
grant execute on function public.search_items_hybrid(text, extensions.vector, integer, integer, integer) to authenticated;
