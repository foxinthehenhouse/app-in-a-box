# Rollback runbook

Roll back the layer that broke, newest first. Decide in under five minutes: if a
release correlates with a new Sentry issue or a `/health` change, roll back first and
debug after.

## OTA

An OTA update is live the next time users open the app, so rolling it back is the
fastest fix for a JS bug.

```bash
cd mobile
eas update:list --branch production --limit 5          # find the last good group id
# Option A: roll back to the previous update on the branch (or to the embedded build)
eas update:rollback --branch production
# Option B: re-publish a specific known-good update group as the newest update
eas update:republish --group <good-group-id> --message "rollback: <reason>"
```

- Clients download the rolled-back update on next launch (and apply it on the one
  after, unless the app checks for updates on launch). Expect a tail of hours.
- Never republish an update built for a different runtime version: the fingerprint
  keeps runtimes apart, and `update:republish` refuses mismatches.
- A crash on launch that prevents the update check: expo-updates falls back to the
  embedded bundle after a failed launch, and a rollback reaches users on retry.

## Native binary

Stores can't un-ship a binary. Options, fastest first:
1. If the bug is in JS, ship an OTA fix on the same runtime (above).
2. App Store Connect: pause the phased release. Play Console: halt the staged rollout.
3. Build and submit a fixed version (expedited review is available for critical bugs).

## Backend

```bash
railway deployment list                    # find the last good deployment
railway redeploy --deployment <id>          # or Railway dashboard: Deployments → ⋯ → Redeploy
curl -s "$API_URL/health?deep=1"            # confirm version = the good sha, db: ok
```

Or revert on GitHub (`git revert <sha>` in a PR) and let Railway deploy `main`. Old
app builds must keep working after the rollback: that's why wire changes are
additive only.

## Database

Migrations are additive, so the old API works against the new schema and rollback
is usually unnecessary: roll the API back and leave the schema.

When you must undo a migration:
1. Every migration header has its rollback SQL (`-- Rollback:`). Run it in a new
   migration file (`supabase migration new rollback_<name>`), never by editing the
   applied one, and apply with `supabase db push` **(owner)**.
2. Dropping a table or column loses data. Take a backup first
   (`supabase db dump --data-only -f backup.sql`) or rely on PITR.
3. Data corruption: Supabase **PITR** (Pro plan add-on) restores to a second; daily
   backups (Pro, 7 days) restore to a day. Free plan: no managed backups, so schedule
   `supabase db dump` yourself before launch.

## After any rollback

- [ ] Sentry: the issue stops getting new events (filter by release).
- [ ] PostHog: the affected funnel recovers.
- [ ] Write it up in `docs/decision-log.md` or an incident note ([incident.md](incident.md)).
