-- NEGATIVE CONTROL for scripts/db-test.sh. Never apply outside that script.
--
-- Plants the mistakes the DB gate exists to catch, inside a transaction that is always
-- rolled back. The script then requires the advisors to report ERROR rows AND the pgTAP
-- suite to report failures. If either stays green here, the gate is blind and the
-- script fails. A guard that cannot fail reads as a guard that passes.

-- An over-broad policy: every user can read and update every profile.
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles for select using (true);
drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles for update using (true) with check (true);

-- A service-only table re-exposed to the API roles.
grant select, update on public.keep_alive to anon, authenticated;
create policy keep_alive_open on public.keep_alive for all using (true);

-- A new table with RLS forgotten, and a hijackable SECURITY DEFINER function that is
-- also left callable by the API roles (Postgres' default EXECUTE to PUBLIC, made
-- explicit here) -- two advisor rows from one function: function_search_path_mutable
-- and security_definer_callable_by_api.
create table public.negctl_unprotected (id int);
create function public.negctl_definer() returns int
  language sql security definer as $$ select 1 $$;
grant execute on function public.negctl_definer() to anon, authenticated;
