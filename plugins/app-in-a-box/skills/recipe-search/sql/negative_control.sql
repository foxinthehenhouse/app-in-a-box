-- recipe-search: append this to supabase/ci/negative_control.sql. scripts/db-test.sh
-- plants it (always rolled back) and requires the pgTAP suite to go red.
--
-- The tempting rewrite of search_items(): SECURITY DEFINER (runs as the owner, so RLS
-- is bypassed) and no user filter. It passes every "does search work" test and returns
-- every user's rows to anyone signed in. supabase/tests/database/search.test.sql must
-- fail on it. (The advisors flag it too, as an API-callable definer; the pgTAP suite
-- is what proves it leaks.)
create or replace function public.search_items(
  p_query text,
  p_limit integer default 20,
  p_after_rank real default null,
  p_after_id uuid default null
)
returns table (id uuid, title text, snippet text, rank real)
language sql stable security definer set search_path = ''
as $$
  select i.id, i.title, i.body, ts_rank_cd(i.search_tsv, q.tsq)::real
  from public.items i, websearch_to_tsquery('simple', coalesce(p_query, '')) as q(tsq)
  where i.search_tsv @@ q.tsq
  order by 4 desc, i.id
  limit least(greatest(coalesce(p_limit, 20), 1), 50)
$$;
