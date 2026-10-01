-- pgTAP in the `extensions` schema, the way Supabase installs it, with that schema on
-- the database's default search_path (Supabase's default is "$user", public, extensions).
-- Idempotent; safe on a real local Supabase stack, where both already hold.
create schema if not exists extensions;
create extension if not exists pgtap with schema extensions;
-- Tests assert while impersonating the API roles, so they need to reach pgTAP too.
grant usage on schema extensions to anon, authenticated, service_role;
do $$
begin
  execute format('alter database %I set search_path = "$user", public, extensions', current_database());
end
$$;
