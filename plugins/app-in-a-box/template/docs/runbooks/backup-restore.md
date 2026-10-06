# Backups and the restore drill

Every night `.github/workflows/backup.yml` dumps the database, encrypts it, and puts it
somewhere that isn't Supabase. Once a month you restore one, to prove it works. Owner
steps are marked **(owner)**.

## Why your own backups

- Supabase's **free plan keeps no backups** at all. Pro keeps 7 daily ones, inside the
  same account and project they'd be rescuing.
- A backup in another provider survives a deleted project, a locked account, or a bad
  migration you only notice a week later.
- PITR (Supabase Pro add-on) is still worth it once there's money or irreplaceable user
  content in the database: it restores to the minute. These nightly dumps are the floor,
  not the ceiling ([rollback.md](rollback.md#database)).

## How it works

`scripts/backup-db.sh`, run by the workflow at 02:23 UTC:

1. `supabase db dump` three times: roles, schema, and data (as `COPY`), the set
   Supabase's own backup guide restores.
2. Tars them and encrypts the tar with [age](https://age-encryption.org) to your
   **public** key (`BACKUP_AGE_RECIPIENT`). Refuses to upload anything that isn't age
   output.
3. Uploads `db/db-<UTC timestamp>.tar.age` to your bucket (any S3-compatible store;
   Cloudflare R2's free tier by default).

GitHub only ever holds the public key, so it can write backups but never read one. The
private key lives with you: a password manager, plus a file outside the repo when you
run a drill. Lose it and every backup is unreadable, so keep two copies.

The script never prints a secret (the database URL holds the password), turns xtrace
off, and scrubs secrets from any CLI error before showing it. `tests/test_backup.py`
checks that with planted leaks, so a later edit that echoes one fails CI.

## Setup (provision step 8 does this)

| Name | Kind | What |
|---|---|---|
| `SUPABASE_DB_URL` | secret | Supabase → Connect → **Session pooler** string with the password filled in. Not the direct `db.<ref>.supabase.co` one: that's IPv6-only and GitHub's runners have no IPv6. |
| `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` | secrets | An API token scoped to the backup bucket only, with object read and write. |
| `BACKUP_AGE_RECIPIENT` | variable | Your age public key (`age1...`). Setting it is what turns the workflow on. Several keys, space-separated, all can decrypt. |
| `BACKUP_S3_BUCKET`, `BACKUP_S3_ENDPOINT` | variables | The bucket, and for R2 `https://<account id>.r2.cloudflarestorage.com` (blank for AWS S3). |
| `BACKUP_S3_REGION` | variable, optional | Default `auto` (R2). Set it for AWS S3. |

**Retention (owner):** add a lifecycle rule on the bucket that deletes objects under
`db/` after 30 days (R2 → the bucket → Settings → Object lifecycle rules). The workflow
never deletes anything, so a leaked bucket token can't be used to wipe the history
through it.

## Is it running?

- Actions → **Backup**: one green run a night. A failed scheduled run emails whoever
  last edited the workflow's schedule.
- GitHub turns scheduled workflows off in a repo with no activity for 60 days and
  emails you first. Re-enable it from the Actions tab.
- The bucket lists one new `db/db-*.tar.age` per night:
  `aws s3 ls "s3://$BACKUP_S3_BUCKET/db/" --endpoint-url "$BACKUP_S3_ENDPOINT"`.

## The restore drill (monthly, and before launch)

A backup nobody has restored is a hope. `scripts/restore-drill.sh` fetches one,
decrypts it, restores it into an EMPTY database in one transaction, and counts the rows
in every table. About ten minutes.

1. **An empty target (owner).** Either a scratch Supabase project (free plan, delete it
   afterwards), or a local stack from an empty folder, not this repo (its stack already
   has your migrations):
   ```bash
   mkdir /tmp/drill && cd /tmp/drill && supabase init && supabase start
   ```
   Its DB URL is `postgresql://postgres:postgres@127.0.0.1:54322/postgres`.
2. **The private key, as a file outside the repo (owner):** for example
   `~/.config/age/<app>-backup.txt`, from your password manager. The drill refuses a key
   file inside the repo.
3. **Pick the newest backup:** the last line of the `aws s3 ls` above. Load the bucket
   credentials the same way as the backup (`AWS_ACCESS_KEY_ID`,
   `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION=auto`, `BACKUP_S3_ENDPOINT`) in your
   shell, never on the command line.
4. **Run it:**
   ```bash
   BACKUP_AGE_IDENTITY_FILE=~/.config/age/<app>-backup.txt \
     scripts/restore-drill.sh "s3://<bucket>/db/db-<timestamp>.tar.age" \
     --target postgresql://postgres:postgres@127.0.0.1:54322/postgres
   ```
   A local `.tar.age` path works too. It refuses a target that already has tables, so it
   can't restore over production by accident.
5. **Check it like a user would:** the row counts look like production's (Supabase →
   Table Editor), and the newest rows are from last night. Then stop the scratch stack
   (`supabase stop --no-backup`) or delete the scratch project, and delete the key file.
6. **Log it** below. A drill that fails is the useful kind: fix the backup first.

**A real restore** is the same steps with a NEW Supabase project as the target, then
point the API at it (Railway variables) and the app (`EXPO_PUBLIC_SUPABASE_*` in EAS,
then an OTA). Users' sessions don't carry over; they sign in again.

## Drill log

| Date | Backup restored | Tables / rows | Took | By | Notes |
|---|---|---|---|---|---|
| | | | | | |

## Rotating the keys

- **Bucket token:** create a new one, update the two GitHub secrets, run the workflow by
  hand (Actions → Backup → Run workflow), then revoke the old one.
- **age key pair:** `age-keygen -o ~/.config/age/<app>-backup-new.txt`, set
  `BACKUP_AGE_RECIPIENT` to the new public key. Keep the OLD private key until the last
  backup made with it has aged out of the bucket (30 days), or those become unreadable.
- **Database password:** see [secrets-rotation.md](secrets-rotation.md); update
  `SUPABASE_DB_URL` in the same sitting.
