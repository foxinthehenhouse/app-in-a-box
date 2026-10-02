-- Offline equivalents of Supabase's security advisors, run against the migrated CI
-- database by scripts/db-test.sh. Each row is `LEVEL|check|object|fix`. Any ERROR row
-- fails the job; WARN rows are printed and kept visible.
--
-- The hosted advisors (`supabase` MCP get_advisors, or the dashboard) check more, but
-- need a live project. These are the ones a migration can break, checked on every PR.
-- Objects owned by an extension (pg_depend deptype 'e', e.g. pgTAP's helper views) are
-- skipped: they are not yours to fix.

-- ERROR rls_disabled_in_public: the anon key ships in every app binary, so a public
-- table without RLS is readable (and often writable) by anyone.
select 'ERROR', 'rls_disabled_in_public', format('%I.%I', n.nspname, c.relname),
       'alter table ... enable row level security, then add policies'
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity
  and not exists (select 1 from pg_depend d where d.objid = c.oid and d.deptype = 'e')

union all
-- ERROR function_search_path_mutable: a SECURITY DEFINER function without a pinned
-- search_path can be hijacked by an object created earlier on the path.
select 'ERROR', 'function_search_path_mutable', format('%I.%I', n.nspname, p.proname),
       'add `set search_path = ''''` to the function definition'
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.prosecdef
  and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
  and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) cfg where cfg like 'search_path=%')

union all
-- ERROR security_definer_callable_by_api: a SECURITY DEFINER function runs as its owner
-- (bypassing RLS); Postgres grants EXECUTE to PUBLIC by default, so unless it is revoked
-- the anon key can call it over PostgREST. Trigger functions are skipped: the API can't
-- call them. The static twin is tests/test_prod_migrations.py::unrestricted_definers.
select 'ERROR', 'security_definer_callable_by_api',
       format('%I.%I(%s)', n.nspname, p.proname, pg_get_function_identity_arguments(p.oid)),
       'revoke execute ... from public, anon, authenticated; grant execute ... to service_role'
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.prosecdef and p.prorettype <> 'trigger'::regtype
  and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
  and (has_function_privilege('anon', p.oid, 'execute')
       or has_function_privilege('authenticated', p.oid, 'execute'))

union all
-- ERROR security_definer_view: a view runs with its owner's rights and bypasses the
-- caller's RLS unless it is security_invoker.
select 'ERROR', 'security_definer_view', format('%I.%I', n.nspname, c.relname),
       'create view ... with (security_invoker = true)'
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'v'
  and not exists (select 1 from pg_depend d where d.objid = c.oid and d.deptype = 'e')
  and not coalesce(c.reloptions @> array['security_invoker=true'], false)

union all
-- WARN auth_rls_initplan: `auth.uid()` evaluated per row instead of once. Wrap it:
-- `using ((select auth.uid()) = user_id)`. A performance issue, not a hole.
select 'WARN', 'auth_rls_initplan', format('%I.%I policy %I', schemaname, tablename, policyname),
       'wrap auth.uid() as (select auth.uid()) in the policy'
from pg_policies
where schemaname = 'public'
  and (coalesce(qual, '') ~ 'auth\.uid\(\)' or coalesce(with_check, '') ~ 'auth\.uid\(\)')
  and not (coalesce(qual, '') || coalesce(with_check, '')) ~* 'select\s+auth\.uid\(\)'

union all
-- WARN rls_enabled_no_policy on a table the API roles can still reach by grant: every
-- query returns nothing. Intended for service-only tables; revoke the grants to say so.
select 'WARN', 'rls_enabled_no_policy', format('%I.%I', n.nspname, c.relname),
       'add policies, or `revoke all ... from anon, authenticated` if service-only'
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity
  and not exists (select 1 from pg_policies pp where pp.schemaname = n.nspname and pp.tablename = c.relname)
  and (has_table_privilege('anon', c.oid, 'select') or has_table_privilege('authenticated', c.oid, 'select'));
