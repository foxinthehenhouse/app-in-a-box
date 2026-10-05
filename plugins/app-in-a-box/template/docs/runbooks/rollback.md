# Rollback runbook

Roll back the layer that broke, newest first. Decide in under five minutes: if a
release correlates with a new Sentry issue or a `/health` change, roll back first and
debug after.

## OTA

An OTA update is live the next time users open the app, so rolling it back is the
fastest fix for a JS bug.

```bash
scripts/rollback-ota.sh                               # plan: shows the latest update group on production
scripts/rollback-ota.sh --yes -m "crash on checkout"  # roll it back
```

If the bad update is still a **staged rollout** (10% of users, waiting on its
approval; see [release.md](release.md#staged-ota-rollout)), reject the approval in the
workflow run first, then run the script: it sees the rollout and runs
`eas update:revert-update-rollout --group <group> --non-interactive` instead, which
puts those users back on the update the rollout started from.

Otherwise the script finds the newest update group on the `production` branch (or
`--runtime <v>`'s newest) and runs `eas update:rollback <group> --non-interactive`.
That republishes the update before it on the same runtime, or rolls back to the
build's embedded bundle if there is none. `update:rollback` only accepts a branch's
latest group, so roll back one release at a time. eas-cli has no dry-run, which is
why the script plans by default. Options: `--branch`, `--platform ios|android`.

To jump straight to a specific known-good group instead:
`cd mobile && eas update:republish --group <good-group-id> --message "rollback: <reason>"`
(`eas update:list --branch production` shows the group ids).

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
