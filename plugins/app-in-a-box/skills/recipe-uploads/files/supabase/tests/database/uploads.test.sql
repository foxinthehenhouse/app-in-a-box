-- Upload bucket policies (pgTAP), added by the recipe-uploads skill.
--
-- Storage runs each request as the caller's role with their JWT claims, so inserting
-- into storage.objects here as `authenticated` is exactly what an upload with a user
-- session does. Two users, A and B; A tries to read, write, move and delete B's files,
-- and files in another bucket under A's own folder name. The negative control in
-- supabase/ci/negative_control.sql re-opens one policy and these must go red.
begin;
create extension if not exists pgtap;
select plan(22);

insert into auth.users (id, email) values
  ('11111111-1111-4111-8111-111111111111', 'a@example.com'),
  ('22222222-2222-4222-8222-222222222222', 'b@example.com');

-- Another bucket that A's folder name also appears in: the policies must not reach it.
insert into storage.buckets (id, name, public) values ('other', 'other', false)
  on conflict (id) do nothing;
insert into storage.objects (bucket_id, name, metadata) values
  ('uploads', '11111111-1111-4111-8111-111111111111/aaaaaaaa-0000-4000-8000-000000000001',
   '{"size": 2048, "mimetype": "image/jpeg"}'),
  ('uploads', '22222222-2222-4222-8222-222222222222/bbbbbbbb-0000-4000-8000-000000000001',
   '{"size": 2048, "mimetype": "image/png"}'),
  ('uploads', '22222222-2222-4222-8222-222222222222/bbbbbbbb-0000-4000-8000-000000000002',
   '{"size": 99999999, "mimetype": "image/jpeg"}'),
  ('other', '11111111-1111-4111-8111-111111111111/not-an-upload', '{}');
insert into public.uploads (id, user_id, path, content_type, size_bytes) values
  ('bbbbbbbb-0000-4000-8000-000000000001', '22222222-2222-4222-8222-222222222222',
   '22222222-2222-4222-8222-222222222222/bbbbbbbb-0000-4000-8000-000000000001', 'image/png', 2048);

-- ---- the bucket --------------------------------------------------------------------------
select is((select public from storage.buckets where id = 'uploads'), false, 'the uploads bucket is private');
select is((select file_size_limit from storage.buckets where id = 'uploads'), 10485760::bigint,
  'the bucket caps a file at 10 MB');
select is((select allowed_mime_types from storage.buckets where id = 'uploads'),
  array['image/jpeg', 'image/png', 'image/webp', 'image/heic'], 'the bucket only takes images');

-- ---- as user A ---------------------------------------------------------------------------
set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-4111-8111-111111111111", "role": "authenticated"}';

select results_eq(
  $$ select name from storage.objects where bucket_id = 'uploads' $$,
  $$ values ('11111111-1111-4111-8111-111111111111/aaaaaaaa-0000-4000-8000-000000000001') $$,
  'a user sees exactly their own files'
);
select is_empty(
  $$ select 1 from storage.objects where name like '22222222-2222-4222-8222-222222222222/%' $$,
  'a user cannot read another user''s file'
);
select is_empty(
  $$ select 1 from storage.objects where bucket_id = 'other' $$,
  'the policies do not reach another bucket, even under the user''s folder name'
);
select lives_ok(
  $$ insert into storage.objects (bucket_id, name, metadata) values
     ('uploads', '11111111-1111-4111-8111-111111111111/aaaaaaaa-0000-4000-8000-000000000002', '{}') $$,
  'a user can upload into their own folder'
);
select throws_ok(
  $$ insert into storage.objects (bucket_id, name) values
     ('uploads', '22222222-2222-4222-8222-222222222222/planted') $$,
  '42501', null, 'a user cannot upload into another user''s folder'
);
select throws_ok(
  $$ insert into storage.objects (bucket_id, name) values ('uploads', 'loose.jpg') $$,
  '42501', null, 'a user cannot upload outside any folder'
);
select throws_ok(
  $$ insert into storage.objects (bucket_id, name) values
     ('other', '11111111-1111-4111-8111-111111111111/x') $$,
  '42501', null, 'a user cannot upload into another bucket'
);
select throws_ok(
  $$ update storage.objects
        set name = '22222222-2222-4222-8222-222222222222/moved'
      where name = '11111111-1111-4111-8111-111111111111/aaaaaaaa-0000-4000-8000-000000000001' $$,
  '42501', null, 'a user cannot move their file into another user''s folder'
);
-- RLS turns a forbidden DELETE / UPDATE into "0 rows", not an error; checked after reset.
select lives_ok(
  $$ delete from storage.objects where name like '22222222-2222-4222-8222-222222222222/%' $$,
  'deleting another user''s files runs (and must remove nothing)'
);
select lives_ok(
  $$ delete from storage.objects
      where name = '11111111-1111-4111-8111-111111111111/aaaaaaaa-0000-4000-8000-000000000002' $$,
  'a user can delete their own file'
);
select is_empty($$ select 1 from public.uploads $$, 'a user cannot read another user''s upload rows');
select throws_ok(
  $$ insert into public.uploads (id, user_id, path, content_type, size_bytes) values
     ('aaaaaaaa-0000-4000-8000-000000000009', '11111111-1111-4111-8111-111111111111',
      '11111111-1111-4111-8111-111111111111/aaaaaaaa-0000-4000-8000-000000000009', 'image/jpeg', 1) $$,
  '42501', null, 'a user cannot write upload rows directly (only record_upload can)'
);
select throws_ok(
  $$ select public.record_upload('11111111-1111-4111-8111-111111111111',
       'aaaaaaaa-0000-4000-8000-000000000001', 10485760, array['image/jpeg']) $$,
  '42501', null, 'the API roles cannot call record_upload (service role only)'
);

-- ---- as anon (the key inside every app binary) ------------------------------------------
reset role;
set local role anon;
set local request.jwt.claims = '{"role": "anon"}';
select is_empty($$ select 1 from storage.objects where bucket_id = 'uploads' $$, 'anon sees no files');
select throws_ok(
  $$ insert into storage.objects (bucket_id, name) values ('uploads', 'anon/x') $$,
  '42501', null, 'anon cannot upload'
);

-- ---- record_upload, as the backend calls it ---------------------------------------------
reset role;
select is(
  (public.record_upload('22222222-2222-4222-8222-222222222222', 'bbbbbbbb-0000-4000-8000-000000000001',
     10485760, array['image/jpeg', 'image/png'])).size_bytes,
  2048::bigint,
  'record_upload records size and type from storage, and a replay returns the same row'
);
select throws_ok(
  $$ select public.record_upload('22222222-2222-4222-8222-222222222222',
       'bbbbbbbb-0000-4000-8000-000000000002', 10485760, array['image/jpeg']) $$,
  '23514', null, 'record_upload refuses a stored object over the size limit'
);
select throws_ok(
  $$ select public.record_upload('11111111-1111-4111-8111-111111111111',
       'bbbbbbbb-0000-4000-8000-000000000001', 10485760, array['image/png']) $$,
  'P0002', null, 'record_upload only finds objects in the named user''s own folder'
);

-- ---- what A's attempts actually changed ---------------------------------------------------
select is(
  (select count(*)::int from storage.objects where name like '22222222-2222-4222-8222-222222222222/%'),
  2,
  'another user''s files are all still there'
);

select * from finish();
rollback;
