-- __APP_NAME__: initial schema.
-- Conventions (see .claude/rules/db-migrations.md): additive + reversible, RLS on
-- every table, user-owned rows keyed by user_id -> auth.users with cascade.
-- Rollback: drop table public.keep_alive; drop table public.profiles;

-- Profiles: one row per auth user, created on sign-up by trigger.
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text check (char_length(display_name) <= 80),
  onboarded boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);
drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own" on public.profiles
  for insert with check (auth.uid() = id);
drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  insert into public.profiles (id) values (new.id) on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Keep-alive: free-tier Supabase pauses after 7 idle days. A daily GitHub Action
-- PATCHes this single row (.github/workflows/supabase-keepalive.yml).
-- RLS on with no policies = service role only.
create table if not exists public.keep_alive (
  id smallint primary key default 1 check (id = 1),
  last_ping_at timestamptz not null default now()
);
alter table public.keep_alive enable row level security;
revoke all on public.keep_alive from anon, authenticated;
insert into public.keep_alive (id) values (1) on conflict (id) do nothing;
