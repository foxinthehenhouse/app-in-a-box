-- Image uploads (recipe-uploads): a PRIVATE Storage bucket, per-user folder policies on
-- storage.objects, and public.uploads, the record of what each user has uploaded.
--
-- Paths are `<auth user id>/<uuid>`. The backend picks them and signs upload URLs with
-- the service key; these policies are the wall for everything else (the app holds a
-- user session and the anon key, so it could call Storage directly).
-- The bucket enforces the size and type limits on the bytes themselves; keep them in
-- step with backend/services/uploads_service.py (tests/test_uploads.py compares).
--
-- Rollback:
--   drop function if exists public.record_upload(uuid, uuid, bigint, text[]);
--   drop table if exists public.uploads;
--   drop policy if exists "uploads_select_own" on storage.objects;
--   drop policy if exists "uploads_insert_own" on storage.objects;
--   drop policy if exists "uploads_update_own" on storage.objects;
--   drop policy if exists "uploads_delete_own" on storage.objects;
--   Then empty and delete the bucket from the dashboard (Storage refuses SQL deletes).

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'uploads', 'uploads', false, 10485760,
  array['image/jpeg', 'image/png', 'image/webp', 'image/heic']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- A user reads and writes only inside their own folder of this bucket. Both halves
-- matter: drop the bucket check and these open every other bucket's files; drop the
-- folder check and every user reads everyone's. supabase/tests/database/uploads.test.sql
-- proves each half.
drop policy if exists "uploads_select_own" on storage.objects;
create policy "uploads_select_own" on storage.objects
  for select to authenticated
  using (bucket_id = 'uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "uploads_insert_own" on storage.objects;
create policy "uploads_insert_own" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "uploads_update_own" on storage.objects;
create policy "uploads_update_own" on storage.objects
  for update to authenticated
  using (bucket_id = 'uploads' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "uploads_delete_own" on storage.objects;
create policy "uploads_delete_own" on storage.objects
  for delete to authenticated
  using (bucket_id = 'uploads' and (storage.foldername(name))[1] = (select auth.uid())::text);

-- One row per completed upload: what the app lists and the data export includes.
-- Rows cascade with the account; the objects themselves are removed by the backend
-- (erasure_service.purge_storage, which empties every USER_FILE_BUCKETS bucket) before
-- the auth user is deleted.
create table if not exists public.uploads (
  id uuid primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  path text not null unique,
  content_type text not null,
  size_bytes bigint not null check (size_bytes > 0),
  created_at timestamptz not null default now(),
  constraint uploads_path_in_own_folder check (path = user_id::text || '/' || id::text)
);
create index if not exists uploads_user_created_idx
  on public.uploads (user_id, created_at desc);

alter table public.uploads enable row level security;
-- Users may read their own rows. No write policies: rows are written by
-- record_upload() (service role) after it has checked the stored object.
drop policy if exists "uploads_select_own" on public.uploads;
create policy "uploads_select_own" on public.uploads
  for select using ((select auth.uid()) = user_id);

-- Record a completed upload, atomically, from what Storage actually stored: the size
-- and type come from storage.objects.metadata, never from the client.
--   P0002 (-> 404) nothing at the path yet; 23514 (-> 422) too big / not allowed.
create or replace function public.record_upload(
  p_user_id uuid,
  p_upload_id uuid,
  p_max_bytes bigint,
  p_allowed_types text[]
)
returns public.uploads
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_path text := p_user_id::text || '/' || p_upload_id::text;
  v_meta jsonb;
  v_size bigint;
  v_type text;
  v_row public.uploads;
begin
  if auth.uid() is not null and auth.uid() <> p_user_id then
    raise exception 'not your account' using errcode = '42501';
  end if;
  select o.metadata into v_meta
    from storage.objects o
   where o.bucket_id = 'uploads' and o.name = v_path;
  if not found then
    raise exception 'upload_not_found' using errcode = 'P0002';
  end if;
  v_size := nullif(v_meta ->> 'size', '')::bigint;
  v_type := v_meta ->> 'mimetype';
  if v_size is null or v_size <= 0 or v_size > p_max_bytes
     or v_type is null or not (v_type = any (p_allowed_types)) then
    raise exception 'upload_rejected' using errcode = '23514';
  end if;
  insert into public.uploads (id, user_id, path, content_type, size_bytes)
  values (p_upload_id, p_user_id, v_path, v_type, v_size)
  on conflict (id) do nothing;
  select * into v_row from public.uploads u
   where u.id = p_upload_id and u.user_id = p_user_id;
  return v_row;
end;
$$;
revoke execute on function public.record_upload(uuid, uuid, bigint, text[])
  from public, anon, authenticated;
grant execute on function public.record_upload(uuid, uuid, bigint, text[]) to service_role;
