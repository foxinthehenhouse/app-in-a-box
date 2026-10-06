-- Hybrid search tests (pgTAP), from recipe-search. Copy to
-- supabase/tests/database/search_hybrid.test.sql along with the hybrid migration (the
-- DB gate then needs pgvector: add postgresql-<ver>-pgvector next to pgtap in db.yml).
--
-- Embeddings here are one-hot 1024-d vectors, so "nearest" is exact: e(n) is the unit
-- vector on axis n. User B again owns the best match on both sides.
begin;
create extension if not exists pgtap;
select plan(7);

create function pg_temp.e(n int) returns extensions.vector language sql as $$
  select (select array_agg(case when g = n then 1 else 0 end order by g)
          from generate_series(1, 1024) g)::real[]::extensions.vector
$$;

insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'a@example.com'),
  ('22222222-2222-4222-8222-222222222222', 'b@example.com');

insert into public.items (id, user_id, title, body, embedding) values
  -- A1 matches the text AND sits nearest the query vector: it must come first.
  ('a0000000-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111', 'Tomato plan', 'water daily', pg_temp.e(1)),
  -- A2 matches the text only.
  ('a0000000-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111', 'Shopping', 'buy tomato paste', pg_temp.e(500)),
  -- A3 has no text match but is close in meaning (a vector-only hit).
  ('a0000000-0000-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111', 'Passata', 'sauce for pasta', null),   -- embedding set below
  -- A4 has no embedding yet: still found by text.
  ('a0000000-0000-4000-8000-000000000004', '11111111-1111-4111-8111-111111111111', 'Tomato seeds', 'sow in spring', null),
  ('b0000000-0000-4000-8000-000000000001', '22222222-2222-4222-8222-222222222222', 'Tomato tomato', 'tomato secret', pg_temp.e(1));

-- A3: almost the query direction (axis 1 plus a little of axis 2), so it ranks just below A1.
update public.items
   set embedding = (select array_agg(case when g = 1 then 1 when g = 2 then 0.2 else 0 end order by g)
                    from generate_series(1, 1024) g)::real[]::extensions.vector
 where id = 'a0000000-0000-4000-8000-000000000003';

select ok(
  (select not p.prosecdef from pg_proc p where p.proname = 'search_items_hybrid'),
  'search_items_hybrid is SECURITY INVOKER, so the caller''s RLS applies'
);

set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated"}';

select is(
  (select array_agg(id::text order by id) from public.search_items_hybrid('tomato', pg_temp.e(1))),
  array['a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
        'a0000000-0000-4000-8000-000000000003', 'a0000000-0000-4000-8000-000000000004'],
  'hybrid returns only the caller''s rows: text hits, vector hits, and rows with no embedding'
);

select is(
  (select id::text from public.search_items_hybrid('tomato', pg_temp.e(1)) limit 1),
  'a0000000-0000-4000-8000-000000000001',
  'a row found by both text and meaning ranks first (RRF sums both lists)'
);

select results_eq(
  $$ select id::text from public.search_items_hybrid('marinara', pg_temp.e(1)) $$,
  $$ values ('a0000000-0000-4000-8000-000000000001'), ('a0000000-0000-4000-8000-000000000003'),
            ('a0000000-0000-4000-8000-000000000002') $$,
  'with no matching word, rows are found by meaning, nearest first'
);

select is(
  (select array_agg(id::text order by id) from public.search_items_hybrid('tomato', null)),
  array['a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000002',
        'a0000000-0000-4000-8000-000000000004'],
  'with no query embedding (provider down) it degrades to text search'
);

reset role;
set local role anon;
set local request.jwt.claims = '{"role": "anon"}';
select throws_ok(
  $$ select * from public.search_items_hybrid('tomato', null) $$,
  '42501', null, 'anon cannot call search_items_hybrid'
);

reset role;
set local role service_role;
set local request.jwt.claims = '{"role": "service_role"}';
select is_empty(
  $$ select 1 from public.search_items_hybrid('tomato', null) $$,
  'a call with no user (the service key) returns nothing'
);

reset role;
select * from finish();
rollback;
