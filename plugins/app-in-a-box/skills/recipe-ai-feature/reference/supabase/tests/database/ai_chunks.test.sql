-- Retrieval isolation (pgTAP): user B can never retrieve user A's chunks, by any path
-- the API roles have. Added by the recipe-ai-feature skill with the ai_chunks migration.
--
-- The embeddings are all the same vector, so similarity is 1 for every row: if the
-- functions or policies let another user's row through, nothing else would hide it.
begin;
create extension if not exists pgtap;
select plan(9);

insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'a@example.com'),
  ('22222222-2222-4222-8222-222222222222', 'b@example.com');

create temporary table v as
  select array_fill(0.1::real, array[1024])::extensions.vector::text as vec;
grant select on v to authenticated, anon, service_role;

-- ---- as user A: index one source ------------------------------------------------------
set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated"}';

select is(
  public.ai_chunks_replace('note-1', 'A secret', jsonb_build_array(
    jsonb_build_object('ord', 0, 'content', 'A''s private note', 'embedding', (select vec from v)))),
  1,
  'a user can index their own text'
);
select is(
  (select count(*)::int from public.ai_match_chunks((select vec from v)::extensions.vector, 6, 0)),
  1,
  'a user retrieves their own chunk'
);

-- ---- as user B ----------------------------------------------------------------------------
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "22222222-2222-4222-8222-222222222222", "role": "authenticated"}';

select is_empty(
  $$ select 1 from public.ai_match_chunks((select vec from v)::extensions.vector, 20, 0) $$,
  'another user''s chunks never come back from retrieval'
);
select is_empty($$ select 1 from public.ai_chunks $$, 'another user''s chunks are not readable');
select throws_ok(
  $$ insert into public.ai_chunks (user_id, source_id, ord, content, embedding)
     values ('11111111-1111-4111-8111-111111111111', 'x', 0, 'planted', (select vec from v)::extensions.vector) $$,
  '42501',
  null,
  'a user cannot write a chunk into someone else''s store'
);
select lives_ok(
  $$ select public.ai_chunks_replace('note-1', '', '[]'::jsonb) $$,
  'replacing a source id that only someone else uses runs (and must delete nothing)'
);

-- ---- as anon, and as the service role (no auth.uid(): must see nothing) -------------------
reset role;
set local role anon;
set local request.jwt.claims = '{"role": "anon"}';
select throws_ok(
  $$ select * from public.ai_match_chunks((select vec from v)::extensions.vector) $$,
  '42501',
  null,
  'anon cannot call retrieval'
);

reset role;
set local role service_role;
set local request.jwt.claims = '{"role": "service_role"}';
select is_empty(
  $$ select 1 from public.ai_match_chunks((select vec from v)::extensions.vector, 20, 0) $$,
  'the service key gets nothing from retrieval (no caller, no rows) instead of everyone''s'
);

reset role;
select is(
  (select count(*)::int from public.ai_chunks where user_id = '11111111-1111-4111-8111-111111111111'),
  1,
  'user A''s chunk survived user B''s attempts'
);

select * from finish();
rollback;
