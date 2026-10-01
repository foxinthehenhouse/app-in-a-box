---
description: Migration safety (additive, RLS, verify live schema)
globs: supabase/migrations/**
---
- **Additive + reversible.** Prefer new columns/tables over altering or dropping. Put
  the rollback SQL in the header comment.
- **RLS on every new table**, with `user_id uuid references auth.users(id) on delete
  cascade` and select/insert/update policies on `auth.uid() = user_id`. Service-only
  tables: RLS on, no policies, `revoke all ... from anon, authenticated`.
- Write policies with `(select auth.uid())`, not bare `auth.uid()`: same meaning,
  evaluated once per statement instead of per row (advisor `auth_rls_initplan`).
- **Never edit an applied migration.** Add a new timestamped file.
- Verify the *live* schema with a `select` before assuming a column exists. Ledgers lie.
- Applying to the hosted DB (`supabase db push`) is an owner action; propose it, don't
  assume it ran.
