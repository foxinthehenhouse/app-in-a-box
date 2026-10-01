-- __APP_NAME__: push notification tokens + Expo tickets, and the ATOMIC WRITE PATTERN.
--
-- register_push_token() is the template's worked example of a multi-row write done
-- right: one Postgres function = one transaction, so "upsert this token" and "prune the
-- user's oldest tokens beyond the cap" commit together or not at all. Copy its shape:
--   * `security definer set search_path = ''`   (fully-qualify every name inside)
--   * takes p_user_id from the backend (the verified token's sub, never a body field),
--     rejects a mismatched auth.uid() if it is ever called with a user JWT, and checks
--     the user exists
--   * raises with an errcode that backend/db.py:rpc() maps to an HTTP status
--   * execute revoked from public/anon/authenticated, granted to service_role only
--
-- Rollback:
--   drop function if exists public.register_push_token(uuid, text, text, integer);
--   drop table if exists public.push_tickets;
--   drop table if exists public.push_tokens;

create table if not exists public.push_tokens (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  -- Unique across users: a device token belongs to whoever signed in on it last.
  token text not null unique
    check (char_length(token) <= 256 and token ~ '^Expo(nent)?PushToken\[.+\]$'),
  platform text check (platform in ('ios', 'android', 'web')),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);
create index if not exists push_tokens_user_idx
  on public.push_tokens (user_id, last_seen_at desc);

alter table public.push_tokens enable row level security;
-- Users may read and remove their own tokens. No insert/update policy on purpose:
-- writes go through register_push_token() so the cap and the hand-over stay atomic.
drop policy if exists "push_tokens_select_own" on public.push_tokens;
create policy "push_tokens_select_own" on public.push_tokens
  for select using (auth.uid() = user_id);
drop policy if exists "push_tokens_delete_own" on public.push_tokens;
create policy "push_tokens_delete_own" on public.push_tokens
  for delete using (auth.uid() = user_id);

-- Expo push tickets awaiting a receipt (checked by /internal/cron/push-receipts).
-- Service-only: RLS on, no policies.
create table if not exists public.push_tickets (
  ticket_id text primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  token text not null,
  created_at timestamptz not null default now()
);
create index if not exists push_tickets_created_idx on public.push_tickets (created_at);
alter table public.push_tickets enable row level security;
revoke all on public.push_tickets from anon, authenticated;

create or replace function public.register_push_token(
  p_user_id uuid,
  p_token text,
  p_platform text default null,
  p_max_tokens integer default 10
)
returns void
language plpgsql
security definer set search_path = ''
as $$
begin
  if p_user_id is null or p_token is null then
    raise exception 'user and token are required' using errcode = '22023';
  end if;
  if p_max_tokens is null or p_max_tokens < 1 then
    raise exception 'p_max_tokens must be >= 1' using errcode = '22023';
  end if;
  -- Ownership: with a user JWT you may only act for yourself (service role has no uid).
  if auth.uid() is not null and auth.uid() <> p_user_id then
    raise exception 'not your account' using errcode = '42501';
  end if;
  if not exists (select 1 from auth.users u where u.id = p_user_id) then
    raise exception 'unknown user' using errcode = '42501';
  end if;

  insert into public.push_tokens as t (user_id, token, platform)
  values (p_user_id, p_token, p_platform)
  on conflict (token) do update
    set user_id = excluded.user_id,
        platform = coalesce(excluded.platform, t.platform),
        last_seen_at = now();

  -- Keep only this user's newest p_max_tokens devices.
  delete from public.push_tokens t
  where t.user_id = p_user_id
    and t.id not in (
      select k.id from public.push_tokens k
      where k.user_id = p_user_id
      order by k.last_seen_at desc, k.id desc
      limit p_max_tokens
    );
end;
$$;

revoke execute on function public.register_push_token(uuid, text, text, integer)
  from public, anon, authenticated;
grant execute on function public.register_push_token(uuid, text, text, integer)
  to service_role;
