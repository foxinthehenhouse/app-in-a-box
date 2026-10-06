-- __APP_NAME__: per-user daily AI token budget (the cost cap), shared by every API instance.
--
-- Not in memory: the API runs several workers, and a cap per process is N caps. One
-- row per user per UTC day; ai_usage_add() adds this call's tokens and says whether the
-- user is still under the cap, in one statement (no read-then-write race). The backend
-- calls it twice: with zeros before a model call (429 `ai_daily_limit` when over), and
-- with the real usage after. Service-only: users never touch this table directly.
--
-- Rollback:
--   drop function if exists public.ai_usage_add(uuid, integer, integer, integer);
--   drop table if exists public.ai_usage;

create table if not exists public.ai_usage (
  user_id uuid not null references auth.users (id) on delete cascade,
  day date not null default (now() at time zone 'utc')::date,
  input_tokens integer not null default 0 check (input_tokens >= 0),
  output_tokens integer not null default 0 check (output_tokens >= 0),
  primary key (user_id, day)
);
alter table public.ai_usage enable row level security;
revoke all on public.ai_usage from anon, authenticated;

create or replace function public.ai_usage_add(
  p_user_id uuid,
  p_in integer,
  p_out integer,
  p_cap integer
)
returns boolean
language plpgsql
security definer set search_path = ''
as $$
declare
  v_total integer;
begin
  if p_user_id is null or p_cap is null or p_cap < 1
     or coalesce(p_in, 0) < 0 or coalesce(p_out, 0) < 0 then
    raise exception 'invalid usage' using errcode = '22023';
  end if;
  insert into public.ai_usage as u (user_id, day, input_tokens, output_tokens)
  values (p_user_id, (now() at time zone 'utc')::date, coalesce(p_in, 0), coalesce(p_out, 0))
  on conflict (user_id, day) do update
    set input_tokens = u.input_tokens + excluded.input_tokens,
        output_tokens = u.output_tokens + excluded.output_tokens
  returning u.input_tokens + u.output_tokens into v_total;
  return v_total < p_cap;
end;
$$;
revoke execute on function public.ai_usage_add(uuid, integer, integer, integer) from public, anon, authenticated;
grant execute on function public.ai_usage_add(uuid, integer, integer, integer) to service_role;
