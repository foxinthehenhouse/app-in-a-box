-- __APP_NAME__: Postgres-backed rate limiting and idempotent scheduled jobs.
--
-- Both are cross-request state, so they live here and not in a Python dict: the API
-- runs several uvicorn workers, each with its own memory (see backend/ratelimit.py).
-- Service-only tables: RLS on, no policies, no grants to anon/authenticated.
--
-- Rollback:
--   drop function if exists public.rate_limit_hit(text, integer);
--   drop table if exists public.rate_limits;
--   drop table if exists public.job_runs;

create table if not exists public.rate_limits (
  key text not null check (char_length(key) <= 200),
  window_start timestamptz not null,
  count integer not null default 0,
  primary key (key, window_start)
);
create index if not exists rate_limits_window_idx on public.rate_limits (window_start);
alter table public.rate_limits enable row level security;
revoke all on public.rate_limits from anon, authenticated;

-- Increment the fixed-window counter for p_key and return the new count, atomically
-- (a single upsert). The backend compares it with the limit. Old windows are deleted
-- by /internal/cron/prune-rate-limits.
create or replace function public.rate_limit_hit(p_key text, p_window_seconds integer)
returns integer
language plpgsql
security definer set search_path = ''
as $$
declare
  v_window timestamptz;
  v_count integer;
begin
  if p_key is null or p_window_seconds is null or p_window_seconds < 1 then
    raise exception 'key and a positive window are required' using errcode = '22023';
  end if;
  v_window := to_timestamp(
    floor(extract(epoch from clock_timestamp()) / p_window_seconds) * p_window_seconds
  );
  insert into public.rate_limits as r (key, window_start, count)
  values (p_key, v_window, 1)
  on conflict (key, window_start) do update set count = r.count + 1
  returning r.count into v_count;
  return v_count;
end;
$$;

revoke execute on function public.rate_limit_hit(text, integer) from public, anon, authenticated;
grant execute on function public.rate_limit_hit(text, integer) to service_role;

-- One row per (job, period) claimed by backend/services/jobs_service.py:claim_run().
-- The primary key is the idempotency guard: a retried or overlapping cron call for
-- the same period fails the insert and skips.
create table if not exists public.job_runs (
  job text not null,
  run_key text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  stats jsonb,
  primary key (job, run_key)
);
alter table public.job_runs enable row level security;
revoke all on public.job_runs from anon, authenticated;
