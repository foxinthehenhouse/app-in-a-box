-- __APP_NAME__: retrieval store for the AI feature (pgvector RAG over the user's OWN text).
--
-- Rollback:
--   drop function if exists public.ai_match_chunks(extensions.vector, integer, double precision);
--   drop function if exists public.ai_chunks_replace(text, text, jsonb);
--   drop table if exists public.ai_chunks;
--   (leave the vector extension installed: other objects may use it)
--
-- Each row is one chunk of something the user wrote, with its embedding. Isolation is
-- enforced HERE, not in Python:
--   * RLS: a user reads, adds and removes only rows where user_id = auth.uid().
--   * Both functions are `security invoker` (RLS applies) AND filter on auth.uid()
--     themselves, so a service-key caller, which bypasses RLS, gets nothing back
--     instead of every user's notes. The backend calls them with the caller's JWT.
--   tests/test_migrations_static.py fails a security definer reader, a reader with no
--   auth.uid() filter, a view without security_invoker, or a vector table with no HNSW
--   index; supabase/tests/database/ai_chunks.test.sql proves it on a real Postgres.
--
-- The dimension (1024) must match EMBEDDINGS_DIM in backend/services/ai_ask.py and the
-- embedding model. Changing models means re-embedding: new column, backfill, swap.
-- Retrieval turns on hnsw.iterative_scan (pgvector >= 0.8, at the bottom): without it,
-- HNSW stops after ef_search candidates, so a user whose rows are a small share of the
-- table can get fewer matches than asked for, or none.

create schema if not exists extensions;
create extension if not exists vector with schema extensions;
grant usage on schema extensions to anon, authenticated, service_role;

create table if not exists public.ai_chunks (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  source_id text not null check (char_length(source_id) between 1 and 200),
  title text not null default '' check (char_length(title) <= 200),
  ord integer not null check (ord >= 0),
  content text not null check (char_length(content) between 1 and 4000),
  embedding extensions.vector(1024) not null,
  created_at timestamptz not null default now(),
  unique (user_id, source_id, ord)
);
create index if not exists ai_chunks_embedding_hnsw
  on public.ai_chunks using hnsw (embedding extensions.vector_cosine_ops);

alter table public.ai_chunks enable row level security;
revoke all on public.ai_chunks from anon;
drop policy if exists "ai_chunks_select_own" on public.ai_chunks;
create policy "ai_chunks_select_own" on public.ai_chunks
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "ai_chunks_insert_own" on public.ai_chunks;
create policy "ai_chunks_insert_own" on public.ai_chunks
  for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists "ai_chunks_delete_own" on public.ai_chunks;
create policy "ai_chunks_delete_own" on public.ai_chunks
  for delete to authenticated using ((select auth.uid()) = user_id);

-- Replace every chunk of one source in one transaction (an empty array deletes it).
create or replace function public.ai_chunks_replace(p_source_id text, p_title text, p_chunks jsonb)
returns integer
language plpgsql
security invoker set search_path = ''
as $$
declare
  v_user uuid := (select auth.uid());
  v_count integer;
begin
  if v_user is null then
    raise exception 'not_authenticated' using errcode = '42501';
  end if;
  if jsonb_typeof(p_chunks) is distinct from 'array' or jsonb_array_length(p_chunks) > 200 then
    raise exception 'chunks must be an array of at most 200' using errcode = '22023';
  end if;
  delete from public.ai_chunks where user_id = v_user and source_id = p_source_id;
  insert into public.ai_chunks (user_id, source_id, title, ord, content, embedding)
  select v_user, p_source_id, coalesce(p_title, ''), (c ->> 'ord')::integer, c ->> 'content',
         (c ->> 'embedding')::extensions.vector
  from jsonb_array_elements(p_chunks) as c;
  get diagnostics v_count = row_count;
  return v_count;
end;
$$;
revoke execute on function public.ai_chunks_replace(text, text, jsonb) from public, anon;
grant execute on function public.ai_chunks_replace(text, text, jsonb) to authenticated;

-- The caller's closest chunks to a query embedding, best first.
create or replace function public.ai_match_chunks(
  p_query extensions.vector(1024),
  p_count integer default 6,
  p_min_similarity double precision default 0.3
)
returns table (id bigint, source_id text, title text, content text, similarity double precision)
language sql
stable
security invoker
set search_path = ''
as $$
  with nearest as materialized (
    select c.id, c.source_id, c.title, c.content,
           1 - (c.embedding operator(extensions.<=>) p_query) as similarity
    from public.ai_chunks c
    where c.user_id = (select auth.uid())
    order by c.embedding operator(extensions.<=>) p_query
    limit least(greatest(coalesce(p_count, 6), 1), 20)
  )
  select * from nearest where similarity >= p_min_similarity order by similarity desc;
$$;
revoke execute on function public.ai_match_chunks(extensions.vector, integer, double precision) from public, anon;
grant execute on function public.ai_match_chunks(extensions.vector, integer, double precision) to authenticated;

-- Iterative index scans (pgvector >= 0.8; Supabase ships it). Older pgvector still
-- answers, just without the fix described in the header.
do $$
begin
  if (select string_to_array(extversion, '.')::int[] >= '{0,8}'
      from pg_extension where extname = 'vector') then
    alter function public.ai_match_chunks(extensions.vector, integer, double precision)
      set hnsw.iterative_scan = 'relaxed_order';
  end if;
end
$$;
