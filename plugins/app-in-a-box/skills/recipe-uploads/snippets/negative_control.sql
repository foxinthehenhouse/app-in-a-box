
-- recipe-uploads: a storage policy that forgot the folder check, so every signed-in user
-- can read every user's files. supabase/tests/database/uploads.test.sql must go red.
drop policy if exists "uploads_select_own" on storage.objects;
create policy "uploads_select_own" on storage.objects
  for select to authenticated using (bucket_id = 'uploads');
