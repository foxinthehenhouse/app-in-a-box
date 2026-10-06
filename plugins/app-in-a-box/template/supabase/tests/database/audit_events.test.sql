-- audit_events is append-only and service-role only (pgTAP).
--
-- Run by scripts/db-test.sh with the RLS tests. Three walls, each checked on its own so
-- that losing one fails here even while the others still hold:
--   1. the API roles (anon, authenticated) can neither read nor write it
--   2. the service role can insert and read, but has no update/delete/truncate grant
--   3. the trigger refuses update/delete/truncate for everyone, superusers included
begin;
create extension if not exists pgtap;
select plan(13);

-- Seeded as the superuser, the way the backend's service-role insert lands.
insert into public.audit_events (actor_id, action, target, request_id) values
  ('11111111-1111-4111-8111-111111111111', 'account.delete', null, 'req-seed-1'),
  ('22222222-2222-4222-8222-222222222222', 'data.export', null, 'req-seed-2');

-- ---- 3. the trigger, which binds even the superuser --------------------------------------
select throws_ok(
  $$ update public.audit_events set action = 'data.export' where request_id = 'req-seed-1' $$,
  '42501',
  null,
  'audit_events: an update is refused, even for the superuser'
);
select throws_ok(
  $$ delete from public.audit_events where request_id = 'req-seed-1' $$,
  '42501',
  null,
  'audit_events: a delete is refused, even for the superuser'
);
select throws_ok(
  $$ truncate public.audit_events $$,
  '42501',
  null,
  'audit_events: a truncate is refused, even for the superuser'
);
select throws_ok(
  $$ insert into public.audit_events (action) values ('Not An Action') $$,
  '23514',
  null,
  'audit_events: an action must look like `noun.verb`'
);

-- ---- 2. the service role: insert + read only ------------------------------------------
set local role service_role;
select lives_ok(
  $$ insert into public.audit_events (actor_id, action, request_id)
     values ('11111111-1111-4111-8111-111111111111', 'role.change', 'req-svc') $$,
  'audit_events: the service role can append'
);
select is(
  (select count(*)::int from public.audit_events where request_id like 'req-%'),
  3,
  'audit_events: the service role can read the trail'
);
-- Checked as privileges, not by trying: the trigger would refuse the attempt anyway (with
-- the same 42501), so an update grant handed back would go unnoticed here.
select ok(
  not has_table_privilege('service_role', 'public.audit_events', 'UPDATE'),
  'audit_events: the service role holds no update grant'
);
select ok(
  not has_table_privilege('service_role', 'public.audit_events', 'DELETE')
    and not has_table_privilege('service_role', 'public.audit_events', 'TRUNCATE'),
  'audit_events: the service role holds no delete or truncate grant'
);

-- ---- 1. the API roles: nothing at all -------------------------------------------------
reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated"}';
select throws_ok(
  $$ select * from public.audit_events $$,
  '42501',
  null,
  'audit_events: a signed-in user cannot read the trail, not even their own rows'
);
select throws_ok(
  $$ insert into public.audit_events (actor_id, action)
     values ('11111111-1111-4111-8111-111111111111', 'account.delete') $$,
  '42501',
  null,
  'audit_events: a signed-in user cannot write a fake entry'
);

reset role;
set local role anon;
set local request.jwt.claims = '{"role": "anon"}';
select throws_ok(
  $$ select * from public.audit_events $$,
  '42501',
  null,
  'audit_events: anon cannot read the trail'
);
select throws_ok(
  $$ insert into public.audit_events (action) values ('account.delete') $$,
  '42501',
  null,
  'audit_events: anon cannot write the trail'
);

-- ---- back as the superuser: the attempts above changed nothing ---------------------------
reset role;
select results_eq(
  $$ select action from public.audit_events where request_id like 'req-%' order by id $$,
  $$ values ('account.delete'), ('data.export'), ('role.change') $$,
  'audit_events: every row is exactly as first written'
);

select * from finish();
rollback;
