-- __APP_NAME__: idempotency keys, so a write replayed with the same key runs once.
--
-- The app replays writes it queued offline, and a replay can be a duplicate (the first
-- attempt committed, the response never arrived). backend/idempotency.py claims
-- (user, key) here before the handler runs and stores the 2xx response on the claim;
-- a second request with that key gets the stored response back. Cross-request state,
-- so it lives here and not in a Python dict (several uvicorn workers).
--
-- Service-only: RLS on, no policies, no grants to anon/authenticated. Rows cascade
-- with the auth user (account deletion), and /internal/cron/prune-rate-limits deletes
-- keys older than a day.
--
-- Rollback:
--   drop function if exists public.idempotency_claim(uuid, text, text, integer, integer);
--   drop table if exists public.idempotency_keys;

create table if not exists public.idempotency_keys (
  user_id uuid not null references auth.users (id) on delete cascade,
  key text not null check (char_length(key) between 8 and 128),
  -- sha256 of method + path + body: the same key on a different request is a 422.
  fingerprint text not null check (char_length(fingerprint) = 64),
  created_at timestamptz not null default now(),
  -- Null until the request finishes with a 2xx; a failed request deletes its claim.
  response_status integer check (response_status between 200 and 299),
  response_body text,
  response_content_type text,
  completed_at timestamptz,
  primary key (user_id, key)
);
create index if not exists idempotency_keys_created_idx on public.idempotency_keys (created_at);
alter table public.idempotency_keys enable row level security;
revoke all on public.idempotency_keys from anon, authenticated;

-- Claim (p_user_id, p_key) for a request with fingerprint p_fingerprint, atomically.
-- Returns one row:
--   claimed = true   the caller owns the key now: run the request, then store or delete.
--   claimed = false  the key is taken; stored_* say by what (fingerprint, and the
--                    stored response, or a null status while it is still running).
-- A claim nobody finished within p_stale_seconds (its worker died), or any claim older
-- than p_ttl_seconds, is taken over as if new.
create or replace function public.idempotency_claim(
  p_user_id uuid,
  p_key text,
  p_fingerprint text,
  p_stale_seconds integer,
  p_ttl_seconds integer
)
returns table (
  claimed boolean,
  stored_fingerprint text,
  stored_status integer,
  stored_body text,
  stored_content_type text
)
language plpgsql
security definer set search_path = ''
as $$
declare
  v_claimed boolean;
begin
  if auth.uid() is not null and auth.uid() <> p_user_id then
    raise exception 'not your account' using errcode = '42501';
  end if;
  if p_key is null or p_fingerprint is null or p_stale_seconds is null
     or p_ttl_seconds is null or p_stale_seconds < 1 or p_ttl_seconds < 1 then
    raise exception 'key, fingerprint and positive windows are required' using errcode = '22023';
  end if;
  insert into public.idempotency_keys as k (user_id, key, fingerprint)
  values (p_user_id, p_key, p_fingerprint)
  on conflict (user_id, key) do update
    set fingerprint = excluded.fingerprint,
        created_at = now(),
        response_status = null,
        response_body = null,
        response_content_type = null,
        completed_at = null
    where (k.response_status is null
           and k.created_at < now() - make_interval(secs => p_stale_seconds))
       or k.created_at < now() - make_interval(secs => p_ttl_seconds)
  returning true into v_claimed;
  if v_claimed then
    return query select true, p_fingerprint, null::integer, null::text, null::text;
    return;
  end if;
  return query
    select false, k.fingerprint, k.response_status, k.response_body, k.response_content_type
      from public.idempotency_keys k
     where k.user_id = p_user_id and k.key = p_key;
end;
$$;

revoke execute on function public.idempotency_claim(uuid, text, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.idempotency_claim(uuid, text, text, integer, integer)
  to service_role;
