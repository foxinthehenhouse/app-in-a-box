-- Minimal stand-ins for the Supabase platform objects the migrations reference, so
-- supabase/migrations/ can be applied to a PLAIN Postgres in CI (.github/workflows/db.yml
-- via scripts/db-test.sh). Ported from the app this kit was extracted from.
--
-- CI / local throwaway databases ONLY. scripts/db-test.sh applies this file only when
-- `auth.users` does not exist yet, so it never runs against a real Supabase stack
-- (`supabase start`, a branch, or a hosted project), where GoTrue owns these objects.
--
-- Scope is what migrations and RLS policies touch (grep before extending):
--   roles anon / authenticated / service_role, with Supabase's default grants
--   auth.users(id)  auth.uid()  auth.role()  auth.jwt()
--   storage.buckets  storage.objects (RLS on)  storage.foldername()   (for file uploads)
-- auth.uid() reads the JWT claims exactly the way Supabase's does, so pgTAP tests can
-- impersonate a user with `set local request.jwt.claims = '{"sub": "..."}'`.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end
$$;

-- Supabase grants the API roles broad table privileges and relies on RLS (and explicit
-- revokes) to fence rows. Mirror that, or an RLS test passes for the wrong reason: a
-- missing GRANT, not a policy, would be what denied the read.
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;

create schema if not exists auth;
grant usage on schema auth to anon, authenticated, service_role;

create table if not exists auth.users (
  id                  uuid primary key default gen_random_uuid(),
  email               text,
  raw_user_meta_data  jsonb,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create or replace function auth.jwt() returns jsonb
language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claims', true), '')::jsonb,
    '{}'::jsonb
  )
$$;

create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(
    coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''), auth.jwt() ->> 'sub'),
    ''
  )::uuid
$$;

create or replace function auth.role() returns text
language sql stable as $$
  select nullif(
    coalesce(nullif(current_setting('request.jwt.claim.role', true), ''), auth.jwt() ->> 'role'),
    ''
  )
$$;

grant execute on all functions in schema auth to anon, authenticated, service_role;

-- Storage: the two tables and the path helper that bucket policies use, shaped like
-- Supabase's (columns a migration or pgTAP test touches). Supabase turns RLS on for
-- storage.objects and grants the API roles table access, so a policy, not a missing
-- GRANT, is what fences each file. Nothing here uploads bytes: CI tests the policies.
create schema if not exists storage;
grant usage on schema storage to anon, authenticated, service_role;

create table if not exists storage.buckets (
  id                  text primary key,
  name                text not null unique,
  owner               uuid,
  public              boolean default false,
  file_size_limit     bigint,
  allowed_mime_types  text[],
  created_at          timestamptz default now(),
  updated_at          timestamptz default now()
);

create table if not exists storage.objects (
  id                uuid primary key default gen_random_uuid(),
  bucket_id         text references storage.buckets (id),
  name              text,
  owner             uuid,
  metadata          jsonb,
  path_tokens       text[] generated always as (string_to_array(name, '/')) stored,
  created_at        timestamptz default now(),
  updated_at        timestamptz default now(),
  last_accessed_at  timestamptz default now(),
  unique (bucket_id, name)
);
alter table storage.buckets enable row level security;
alter table storage.objects enable row level security;
grant all on storage.buckets, storage.objects to anon, authenticated, service_role;

-- 'a/b/c.jpg' -> {a,b}: every folder in the path, without the file name.
create or replace function storage.foldername(name text) returns text[]
language plpgsql immutable as $$
declare
  _parts text[];
begin
  select string_to_array(name, '/') into _parts;
  return _parts[1:array_length(_parts, 1) - 1];
end
$$;
grant execute on all functions in schema storage to anon, authenticated, service_role;
