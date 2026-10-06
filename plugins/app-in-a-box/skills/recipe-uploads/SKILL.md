---
name: recipe-uploads
description: Let users upload photos in an App in a Box app - a private Supabase Storage bucket with per-user folder RLS, signed upload URLs from the backend (rate limited, size and type enforced server-side), files deleted with the account and listed in the data export, and a mobile picker with progress and retry. Use when the owner wants profile photos, avatars, image attachments, "add a picture", receipts, or any user file upload. Covers the apply script, migration, pgTAP tests, env wiring, egress cost and when to move to Cloudflare R2.
---

# Recipe: image uploads (private bucket, signed URLs)

The bytes never pass through the API. The backend checks what the app wants to send,
picks the path (`<user id>/<uuid>`, never from the request) and signs an upload URL for
exactly that object; the app PUTs the file straight to Storage; then the backend reads
what actually landed and records it. Reads hand out short-lived signed URLs: the bucket
is private, so a URL is the only way to see a file.

⚖️ Owner decisions before starting: what users may upload (the recipe ships images
only, 10 MB each), whether anything is ever public (the recipe says never; a public
avatar needs its own bucket and its own policy review), and how long files are kept
(the recipe keeps them until the user deletes them or their account).

## What it adds

| Piece | Where (in the app) |
|---|---|
| Bucket + RLS | `supabase/migrations/<now>_uploads.sql`: private `uploads` bucket with `file_size_limit` + `allowed_mime_types`; `storage.objects` policies (select/insert/update/delete only where `bucket_id = 'uploads'` and the first folder is `auth.uid()`); `public.uploads` table (RLS, read-own); `record_upload()` (service role only) records size and type from `storage.objects.metadata`, never from the client |
| API | `backend/routers/uploads.py`: `POST /api/v1/uploads` (ticket), `POST /api/v1/uploads/{id}/complete`, `GET /api/v1/uploads`, `DELETE /api/v1/uploads/{id}`, each rate limited; logic in `backend/services/uploads_service.py` |
| Account deletion | `_delete_user_files()` in `backend/routers/me.py` calls `uploads_service.delete_user_files()`: lists the user's folder in Storage and removes every object (completed or not) BEFORE the auth user goes; a Storage error fails the deletion instead of orphaning files |
| Data export | an `uploads` reader in `backend/routers/export.py`: every row, each with a signed download link valid for a week |
| Mobile | `lib/uploads.ts` (`useImageUpload()`: pick with expo-image-picker, PUT with progress, retry from the step that failed, `imageUploaded` success/failure analytics), `components/ui/ImageUpload.tsx`, adapters + `*Wire` types in `lib/api.ts`, demo routes, `uploads.*` strings |
| Tests | `tests/test_uploads.py` (scoping, limits, idempotency, deletion, export, rate limits), `supabase/tests/database/uploads.test.sql` (pgTAP: both halves of every policy), a planted policy hole in `supabase/ci/negative_control.sql`, `lib/__tests__/uploads.test.ts`, `components/__tests__/image-upload.test.tsx` |

## Steps

1. **Apply.** From the app root. `$KIT` is the plugin root: `appbox.yaml` → `kit_root`
   if present, else `${CLAUDE_PLUGIN_ROOT}` (Claude Code) or the folder two levels above
   this file (Codex / pasted prompt).
   ```bash
   python3 "$KIT/skills/recipe-uploads/apply.py" .
   ```
   It copies `files/` in (never over an existing file), names the migration for the
   current time, and makes the wiring edits listed in the table above, plus the
   wire-contract pairs in `tests/test_wire_contract.py`, the row in AGENTS.md's
   `## Where things live`, the `expo-image-picker` config plugin in `mobile/app.json`
   (photo library only: camera and microphone permissions off), and, for an app made
   before the kit stubbed Storage, the Storage stubs in `supabase/ci/platform_stubs.sql`
   and the Storage fake in `tests/test_prod_fakes.py`. Re-running is safe. If the app
   has reworked one of those files, it writes nothing and names each edit to make by hand.
2. **Install the picker** (only now, not in the template): `cd mobile && npx expo install expo-image-picker`.
   It is a native module: the next build needs `eas build` (not just an OTA update).
3. **Use it** where the feature lives: `<ImageUpload onUploaded={(u) => save(u.id)} />`,
   or `useImageUpload()` for your own UI. Store the upload `id` on your own row (a
   `uuid references public.uploads (id) on delete set null` column), never the URL: URLs
   expire. Show images with `<Media source={upload.url} />` from `listUploads()`.
4. **Run the gates**: `scripts/dev-venv.sh python -m pytest -q`, `cd mobile && npm run gates`,
   and the DB gate. The migration changes the schema, so refresh the snapshot and commit
   it with the migration: `DATABASE_URL=... scripts/db-test.sh --write-snapshot`, review
   the diff of `supabase/schema-snapshot.txt`, then CI's DB job checks it.
5. **Apply the migration** to production (`supabase db push`, owner-run), then check in
   the dashboard: Storage → `uploads` is **private**, with the 10 MB limit and the four
   image types; Policies shows the four `uploads_*_own` policies on `storage.objects`.
6. Review the diff like any PR: the account-deletion copy (`deleteAccount.whatGoes`) now
   says photos go too; adjust the strings to the app's voice.

To change the limits, change `MAX_BYTES` / `ALLOWED_TYPES` in `uploads_service.py`, the
`ContentType` literal in `routers/uploads.py`, the bucket row (in a NEW migration), and
`MAX_UPLOAD_BYTES` / `UPLOAD_TYPES` in `lib/uploads.ts`. `test_uploads.py` fails until the
API and the migration agree. Never allow `image/svg+xml`: it can carry script.

## Env / wiring checklist

| Where | What |
|---|---|
| Railway | nothing new: the backend signs with the Supabase service key it already has |
| EAS | nothing new (no `EXPO_PUBLIC_*` var); a new build, because expo-image-picker is native |
| FEATURE_CONFIG | nothing new: uploads need only Supabase, which is already registered |
| Supabase | the migration (bucket + policies + table + function); nothing to click |
| App Store privacy labels | "Photos or Videos", linked to the user, for app functionality |

## Egress costs, and when to move to Cloudflare R2

Storage is cheap; **egress** (bytes served) is what grows. Every time a phone downloads a
photo, that is egress. Supabase's plans include a monthly egress allowance and charge per
GB beyond it; Cloudflare R2 charges for storage and operations but nothing for egress.
Check both pricing pages for today's numbers before deciding; they change.

A quick estimate: daily active users × photos viewed per day × average size × 30. 1,000
users viewing 30 photos of 300 KB is about 270 GB a month, which is already past the
allowance of an entry paid plan.

Before moving, cut the bytes (each of these is cheaper than a migration):
- Resize before upload: `quality: 0.8` is set; for avatars or thumbnails also pass a
  smaller size through `expo-image-manipulator` before `putFile`.
- Let phones cache: `expo-image` (the template's `<Media>`) caches on disk; sign
  download URLs for long enough that the cache key stays stable for a session.
- Serve thumbnails in lists, the full image only on tap.

Move to R2 when egress is a real line on the bill after that (it regularly exceeds the
plan's allowance), or when files become shareable outside the app (links in messages,
public galleries), or when you add video. What changes: the backend signs S3-style
presigned URLs for R2 instead (same `UploadTicket` shape, so the app's flow stays), the
app's `putFile` sends the raw file instead of multipart, and **RLS no longer guards the
files**: the backend's path choice and short URL lifetimes are the only fence, so keep
every path built from `user.id` and keep `delete_user_files` (as an R2 prefix delete)
and the export reader. That is a ⚖️ owner call (new vendor, new bill).

## Tests it ships (keep them green)

- Backend: signed path is the caller's folder; a body `userId` or `path` is a 422; gif,
  pdf, svg, oversized and empty requests are refused before anything is signed;
  `complete` records what Storage holds, is idempotent, 404s on another user's id, and
  removes an object that is too big or the wrong type; list and delete are scoped;
  account deletion empties the folder (across list pages, including never-completed
  uploads) and fails rather than orphaning files; export lists only the caller's files;
  every upload route is rate limited; the bucket limits match the API.
- pgTAP: bucket is private with the limits; a user reads, writes, moves and deletes only
  in their own folder of this bucket; another bucket under the same folder name is out of
  reach; anon gets nothing; upload rows are read-own and write-never; `record_upload` is
  service-only and refuses an oversized object. The negative control re-opens the select
  policy without the folder check and the suite must fail.
- Mobile: checks before any request, the PUT with progress and its failure codes, success
  and failure analytics, retry resuming at the failed step, the component's states.

When you add a send site of your own (a screen, a new kind of upload): a Maestro flow
for the screen, and a backend test if you add an endpoint.

## Done means

- [ ] On a preview build, choosing a photo shows progress and then the photo; a row
      appears in `public.uploads` and an object under `uploads/<your user id>/`.
- [ ] Airplane mode mid-upload shows the error with Try again; reconnecting and retrying
      finishes without a second object.
- [ ] As another user, `GET /api/v1/uploads` shows none of the first user's files, and the
      first user's object path returns 400/404 from Storage with the second user's session.
- [ ] Settings → Download my data includes the upload with a working link.
- [ ] Deleting the account removes every object under the user's folder (check Storage).
- [ ] PostHog shows `image_uploaded` with `success: true`, and with `success: false` and an
      `error_code` for the airplane-mode attempt.
