-- Performance: evaluate auth.uid() once per statement, not once per row.
-- Supabase's `auth_rls_initplan` advisor flags bare `auth.uid()` in policies; wrapping
-- it as `(select auth.uid())` lets Postgres hoist it into an InitPlan. Same semantics,
-- so the pgTAP RLS tests in supabase/tests/ must still pass unchanged.
-- Rollback: re-run the policy blocks from 20260101000000_init.sql and
-- 20260315120000_push_tokens.sql (bare auth.uid()).

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
  for select using ((select auth.uid()) = id);
drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own" on public.profiles
  for insert with check ((select auth.uid()) = id);
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
  for update using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

drop policy if exists "push_tokens_select_own" on public.push_tokens;
create policy "push_tokens_select_own" on public.push_tokens
  for select using ((select auth.uid()) = user_id);
drop policy if exists "push_tokens_delete_own" on public.push_tokens;
create policy "push_tokens_delete_own" on public.push_tokens
  for delete using ((select auth.uid()) = user_id);
