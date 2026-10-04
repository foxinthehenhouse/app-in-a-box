-- Search behaviour + isolation tests (pgTAP), from recipe-search. Copy to
-- supabase/tests/database/search.test.sql; scripts/db-test.sh runs it with the others.
--
-- The point of this file: search can't see another user's rows, whoever calls it. User
-- B owns the best match for every term here, so a search_items() that loses its user
-- filter AND bypasses RLS (a SECURITY DEFINER rewrite, the usual "make it faster" edit)
-- puts B's rows in A's results and fails the first two isolation tests.
begin;
create extension if not exists pgtap;
select plan(12);

insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'a@example.com'),
  ('22222222-2222-4222-8222-222222222222', 'b@example.com');

insert into public.items (id, user_id, title, body) values
  -- A: a title hit, two identical body hits (equal rank: the keyset tiebreak), a miss.
  ('a0000000-0000-4000-8000-000000000001', '11111111-1111-4111-8111-111111111111', 'Tomato plan', 'water every morning'),
  ('a0000000-0000-4000-8000-000000000002', '11111111-1111-4111-8111-111111111111', 'Shopping', 'buy tomato paste'),
  ('a0000000-0000-4000-8000-000000000003', '11111111-1111-4111-8111-111111111111', 'Shopping', 'buy tomato paste'),
  ('a0000000-0000-4000-8000-000000000004', '11111111-1111-4111-8111-111111111111', 'Basil', 'pinch the tips'),
  -- B: the strongest match for "tomato", and the only row with "secret".
  ('b0000000-0000-4000-8000-000000000001', '22222222-2222-4222-8222-222222222222', 'Tomato tomato', 'tomato secret recipe');

select ok(
  (select not p.prosecdef from pg_proc p where p.oid = 'public.search_items(text, integer, real, uuid)'::regprocedure),
  'search_items is SECURITY INVOKER, so the caller''s RLS applies'
);

-- ---- as user A ------------------------------------------------------------------------
set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated"}';

select results_eq(
  $$ select id::text from public.search_items('tomato') $$,
  $$ values ('a0000000-0000-4000-8000-000000000001'), ('a0000000-0000-4000-8000-000000000002'),
            ('a0000000-0000-4000-8000-000000000003') $$,
  'a user finds only their own rows, best first: title (A) outranks body (B), ties by id'
);

select is_empty(
  $$ select 1 from public.search_items('secret') $$,
  'a term only another user''s row contains finds nothing'
);

select results_eq(
  $$ select id::text from public.search_items('tomato', 2) $$,
  $$ values ('a0000000-0000-4000-8000-000000000001'), ('a0000000-0000-4000-8000-000000000002') $$,
  'p_limit caps the page'
);

-- The next page starts after the last row's (rank, id): the tied row comes next, once.
select results_eq(
  $$ select s.id::text from public.search_items('tomato', 2,
       (select rank from public.search_items('tomato', 2) offset 1 limit 1),
       'a0000000-0000-4000-8000-000000000002') s $$,
  $$ values ('a0000000-0000-4000-8000-000000000003') $$,
  'the keyset cursor (rank, id) continues past a tie without skipping or repeating'
);

select is(
  (select count(*)::int from public.search_items('tomato', 1000)),
  3,
  'p_limit is clamped (at most 50 a page) and never widens the result past the caller''s rows'
);

select is(
  (select snippet from public.search_items('paste') limit 1),
  'buy tomato paste',
  'the snippet is plain text from the body (no markup for the app to strip)'
);

select results_eq(
  $$ select id::text from public.search_items('"tomato paste" -water') $$,
  $$ values ('a0000000-0000-4000-8000-000000000002'), ('a0000000-0000-4000-8000-000000000003') $$,
  'websearch syntax: a quoted phrase and a -exclusion'
);

select lives_ok(
  $$ select * from public.search_items('(( "unclosed & | ! :*') $$,
  'any user input is a valid query (websearch_to_tsquery never raises)'
);

-- ---- as anon (the key inside every app binary) --------------------------------------------
reset role;
set local role anon;
set local request.jwt.claims = '{"role": "anon"}';

select throws_ok(
  $$ select * from public.search_items('tomato') $$,
  '42501',
  null,
  'anon cannot call search_items'
);

-- ---- as service_role (bypasses RLS; no uid) -----------------------------------------------
reset role;
set local role service_role;
set local request.jwt.claims = '{"role": "service_role"}';

select is_empty(
  $$ select 1 from public.search_items('tomato') $$,
  'a call with no user (the service key) returns nothing, not everyone''s rows'
);

reset role;
select is(
  (select count(*)::int from public.items where title = 'Tomato tomato'),
  1,
  'the other user''s row was there to be found all along'
);

select * from finish();
rollback;
