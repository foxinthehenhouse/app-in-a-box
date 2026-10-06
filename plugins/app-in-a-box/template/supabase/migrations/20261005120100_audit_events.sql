-- __APP_NAME__: an append-only audit trail of sensitive actions.
--
-- Rollback (triggers before their function; the trigger blocks TRUNCATE, not DROP):
--   drop trigger if exists audit_events_no_truncate on public.audit_events;
--   drop trigger if exists audit_events_no_update_delete on public.audit_events;
--   drop function if exists public.audit_events_append_only();
--   drop table if exists public.audit_events;
--
-- One row per account deletion, data export, role change (and anything else you add to
-- backend/services/audit_service.py): who did it, what, to what, under which request id.
-- It is the record you show when someone asks "who exported my data?" or "did you
-- really delete it?", so it must be impossible to rewrite after the fact:
--   * service role only: RLS on with no policies, nothing granted to anon/authenticated,
--     and even the service role can only insert and read (update/delete/truncate revoked)
--   * a trigger refuses UPDATE, DELETE and TRUNCATE for EVERY role, the table owner and
--     superusers included, so a revoked grant re-added by mistake still changes nothing
--
-- actor_id deliberately has NO foreign key to auth.users. A cascade would have to delete
-- rows the trigger forbids deleting (so account deletion would fail), and the point of
-- the trail is that it outlives the account: after deletion actor_id is an id that
-- matches no user, and the rows hold no name, email or payload. Keep it that way:
-- `target` is an id or a vendor name, never personal data.

create table if not exists public.audit_events (
  id bigint generated always as identity primary key,
  -- The verified caller (the token's sub), or null for a system job.
  actor_id uuid,
  action text not null check (action ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
  target text check (char_length(target) <= 200),
  request_id text check (char_length(request_id) <= 128),
  at timestamptz not null default now()
);
create index if not exists audit_events_actor_idx on public.audit_events (actor_id, id);

alter table public.audit_events enable row level security;
revoke all on public.audit_events from anon, authenticated;
revoke update, delete, truncate on public.audit_events from service_role;

create or replace function public.audit_events_append_only()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'audit_events is append-only (% refused)', tg_op
    using errcode = '42501';
end;
$$;

drop trigger if exists audit_events_no_update_delete on public.audit_events;
create trigger audit_events_no_update_delete
  before update or delete on public.audit_events
  for each row execute function public.audit_events_append_only();

drop trigger if exists audit_events_no_truncate on public.audit_events;
create trigger audit_events_no_truncate
  before truncate on public.audit_events
  for each statement execute function public.audit_events_append_only();
