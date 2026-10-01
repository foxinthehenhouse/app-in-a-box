-- RLS behaviour tests (pgTAP). The backend uses the service key and scopes queries
-- itself; RLS is the wall for everything else: the mobile app talks to Supabase
-- directly with the anon key, and that key ships inside every app binary.
--
-- Run by scripts/db-test.sh (CI: .github/workflows/db.yml). Also compatible with
-- `supabase test db` against a local `supabase start` stack.
--
-- Pattern for a new user-owned table: insert rows for two users as the superuser,
-- then `set local role authenticated` + a JWT `sub` claim, try to read / update /
-- delete the other user's rows, `reset role`, and assert nothing changed. Add the
-- cases here and bump plan().
begin;
create extension if not exists pgtap;
select plan(13);

insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'a@example.com'),
  ('22222222-2222-4222-8222-222222222222', 'b@example.com');

select is(
  (select count(*)::int from public.profiles
    where id in ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222')),
  2,
  'sign-up trigger creates one profile per auth user'
);

-- ---- as user A ------------------------------------------------------------------------
set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated"}';

select results_eq(
  $$ select id::text from public.profiles $$,
  $$ values ('11111111-1111-4111-8111-111111111111') $$,
  'a user sees exactly their own profile'
);

select is_empty(
  $$ select 1 from public.profiles where id = '22222222-2222-4222-8222-222222222222' $$,
  'a user cannot read another user''s profile'
);

-- RLS turns a forbidden UPDATE into "0 rows", not an error; checked after reset role.
select lives_ok(
  $$ update public.profiles set display_name = 'pwned'
     where id = '22222222-2222-4222-8222-222222222222' $$,
  'updating another user''s profile runs (and must change nothing)'
);

select lives_ok(
  $$ update public.profiles set display_name = 'Ann'
     where id = '11111111-1111-4111-8111-111111111111' $$,
  'a user can update their own profile'
);

select throws_ok(
  $$ update public.profiles set id = '22222222-2222-4222-8222-222222222222'
     where id = '11111111-1111-4111-8111-111111111111' $$,
  '42501',
  null,
  'a user cannot re-key their row to another user (update WITH CHECK)'
);

select throws_ok(
  $$ select * from public.keep_alive $$,
  '42501',
  null,
  'an authenticated user cannot read keep_alive (service role only)'
);

-- ---- as anon (the key inside every app binary) --------------------------------------------
reset role;
set local role anon;
set local request.jwt.claims = '{"role": "anon"}';

select is_empty($$ select 1 from public.profiles $$, 'anon sees no profiles');

select throws_ok(
  $$ select * from public.keep_alive $$,
  '42501',
  null,
  'anon cannot read keep_alive'
);

select throws_ok(
  $$ update public.keep_alive set last_ping_at = now() $$,
  '42501',
  null,
  'anon cannot write keep_alive'
);

-- ---- back as the superuser: check what the attempts above actually changed ----------------
reset role;

select is(
  (select display_name from public.profiles where id = '22222222-2222-4222-8222-222222222222'),
  null,
  'another user''s profile is unchanged'
);

select is(
  (select display_name from public.profiles where id = '11111111-1111-4111-8111-111111111111'),
  'Ann',
  'the user''s own update landed'
);

select ok(
  (select updated_at > created_at from public.profiles
    where id = '11111111-1111-4111-8111-111111111111'),
  'an update moves updated_at forward (set_updated_at trigger)'
);

select * from finish();
rollback;
