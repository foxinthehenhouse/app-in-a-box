---
description: Migration safety (additive, expand/contract, RLS, verify live schema)
globs: supabase/migrations/**
---
- **Additive + reversible.** Prefer new columns/tables over altering or dropping. Put
  the rollback SQL in the header comment.
- **Expand, then contract.** The app version already on people's phones keeps reading
  the old schema for weeks (store review, users who never update). So a breaking change
  is three releases, never one:
  1. *Expand:* add the new column or table (nullable, or with a default). Old builds
     ignore it.
  2. *Migrate readers:* ship backend + app code that writes both and reads the new one;
     backfill old rows in its own migration.
  3. *Contract:* only once no supported app version reads the old column, drop it in a
     later release.
  Never drop or rename a column (or change its type) that a deployed app version
  reads. A rename is add-new, copy, switch readers, drop-old.
- **Squawk lints every migration** (`scripts/db-lint.sh`, rules in `.squawk.toml`). It
  fails an index built without `concurrently` on an existing table, a `not null` column
  with no default, a rename, a drop or a type change. Fix the shape; don't silence it.
  The Supabase CLI runs each migration file in a transaction, where `concurrently` is
  not allowed: on a table that already holds real rows, run the
  `create index concurrently` by hand (an owner action), then commit a migration with
  `create index if not exists` under `-- squawk-ignore require-concurrent-index-creation`
  and a comment saying so. A table created in the same file needs none of this.
- **Commit the schema snapshot.** `supabase/schema-snapshot.txt` is the schema the
  migrations add up to; CI fails when they disagree. After a schema change run
  `DATABASE_URL=<throwaway Postgres> scripts/db-test.sh --write-snapshot` and commit the
  file with the migration, so the PR shows the schema change in plain text.
- **RLS on every new table**, with `user_id uuid references auth.users(id) on delete
  cascade` and select/insert/update policies on `(select auth.uid()) = user_id`. Service-only
  tables: RLS on, no policies, `revoke all ... from anon, authenticated`.
- Write policies with `(select auth.uid())`, not bare `auth.uid()`: same meaning,
  evaluated once per statement instead of per row (advisor `auth_rls_initplan`).
- **Never edit an applied migration.** Add a new timestamped file.
- Verify the *live* schema with a `select` before assuming a column exists. Ledgers lie.
- Applying to the hosted DB (`supabase db push`) is an owner action; propose it, don't
  assume it ran.
