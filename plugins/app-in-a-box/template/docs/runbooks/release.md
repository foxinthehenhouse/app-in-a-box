# Release runbook

How a change gets from `main` to users, and how the scheduled jobs are wired. Owner
steps are marked **(owner)**: an agent can't press store buttons or set deploy config.

## What ships where

| Layer | Ships by | Rollback |
|---|---|---|
| Backend (FastAPI) | Railway auto-deploys `main` | [rollback.md](rollback.md#backend) |
| Database | `supabase db push` **(owner)** | [rollback.md](rollback.md#database) |
| JS / assets | OTA via EAS Update (`release.yml`, native unchanged), 10% first | [rollback.md](rollback.md#ota) |
| Native binary | EAS Build + Submit (`release.yml`, native changed) | a new build; stores can't un-ship |

## Order of operations (always this order)

1. **Migrations first, additive only.** `supabase db push` **(owner)**. The old API and
   the old app must still work against the new schema (see `.agents/rules/db-migrations.md`).
2. **Backend second.** Merge to `main`; Railway deploys. Check
   `curl -s $API_URL/health?deep=1` → `status: ok`, `db: ok`, `version` = the new sha.
3. **App last.** Fast-forward `release` to `main` and push:
   `git push origin main:release`. `mobile/.eas/workflows/release.yml` fingerprints the
   native layer and either publishes an OTA update to `production` or builds +
   submits to TestFlight / Play internal testing.
4. **OTA: promote or roll back (owner).** The update reaches 10% of users first. Read
   its crash-free sessions ([below](#staged-ota-rollout)), then approve the run's
   "Roll out to 100%" step, or reject it and run `scripts/rollback-ota.sh`.
5. **Store steps (owner):** in App Store Connect add the build to review (use phased
   release); in Play Console promote internal → production with a staged rollout.

Why this order: old app builds stay installed for weeks, so the API must accept what
they send (additive wire changes only), and the schema must accept what both API
versions write.

## Before a store submission

- [ ] The App in a Box production checklist (`docs/PRODUCTION.md` in the kit) is green:
      privacy manifest, nutrition label, account deletion reachable in-app, a demo
      account in the App Review notes.
- [ ] `version` bumped in `mobile/app.json` for a native release (build numbers are
      remote-managed: `appVersionSource: remote`).
- [ ] Sentry release = git sha for the API (Railway sets `RAILWAY_GIT_COMMIT_SHA`).
      The app's Sentry plugin uploads source maps during EAS Build, and every OTA
      update job uploads its own (`upload_sentry_sourcemaps: true`), so both need
      `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` in the EAS environment.

## Staged OTA rollout

An OTA update reaches every user on their next launch, so a bad one is a bad day for
everyone at once. `release.yml` publishes each production update to **10%** of users
(`rollout_percentage: 10`), per platform, and then waits on a "crash-free sessions hold
up? Roll out to 100%" approval in the workflow run on expo.dev.

Each update is its own Sentry release while it runs: `<app id>@<version>+<update id>`
(`mobile/lib/monitoring.ts`), with the update id, group, runtime version and channel
as tags. So its crash-free sessions are a number you can read, and its stack traces
are symbolicated from the source maps its job uploaded.

**Promote when, for that release in Sentry → Releases:**

- [ ] at least 24 hours have passed at 10% (a weekday, if you can: weekend use is thin);
- [ ] crash-free sessions are **99.5% or more**, and no lower than the release before it;
- [ ] no new issue is first seen in this release that a user would hit.

Below about 100 sessions the percentage is noise: wait the 24 hours and read the
release's issues one by one instead.

**Promote:** approve the step in the workflow run (expo.dev → the project →
Workflows → the run). Without the run at hand:
`cd mobile && eas update:edit <group-id> --rollout-percentage 100 --non-interactive`
(`scripts/rollback-ota.sh` prints the exact command while a rollout is in progress).

**Don't promote:** reject the approval and run `scripts/rollback-ota.sh --yes -m
"<reason>"`. It reverts the rollout, so the 10% go back to the previous update
([rollback.md](rollback.md#ota)).

Finish each rollout, one way or the other, before the next release: EAS refuses a new
update on a runtime that still has a rollout in progress, so the next push to
`release` would fail its update job until you do.

## PR previews

`mobile/.eas/workflows/pr-preview.yml` runs on every PR: unchanged native → OTA to branch
`pr-<number>` (open it from the preview build's update picker / dev client); changed
native → a fresh preview build. Previews go to their branch at 100% and never stage: a
rollout in progress would block the PR's next push. Railway PR environments are optional (Railway →
Settings → Environments → enable PR environments) and need their own Supabase branch
or a shared staging project.

## Scheduled jobs (cron)

The API exposes `POST /internal/cron/<job>`, guarded by `X-Cron-Secret`. Jobs:
`weekly-digest` (Mondays), `push-receipts` (every 30 min),
`prune-rate-limits` (daily). Each job is idempotent, so retries are safe.

1. **(owner)** Generate and set the secret on Railway and in GitHub:
   ```bash
   SECRET=$(openssl rand -hex 32)
   railway variables --set "CRON_SECRET=$SECRET"
   gh secret set CRON_SECRET --body "$SECRET"
   gh variable set API_URL --body "https://<your-app>.up.railway.app"
   ```
   Until it is set, every cron call gets a 503 naming "scheduled jobs (cron)" and
   `/health?deep=1` lists it under `features_optional_unconfigured`. Once production
   depends on a job, move the entry from `OPTIONAL_FEATURE_CONFIG` to `FEATURE_CONFIG`
   in `backend/config.py` so its absence degrades `/health`.
2. Pick a scheduler:

**GitHub Actions** (free, no extra service): `.github/workflows/cron.yml`

```yaml
name: cron
on:
  schedule:
    - cron: "7 8 * * 1"      # weekly-digest, Mondays 08:07 UTC
    - cron: "*/30 * * * *"   # push-receipts
    - cron: "17 3 * * *"     # prune-rate-limits
  workflow_dispatch:
    inputs:
      job: { description: "job name", required: true }
permissions: {}
jobs:
  call:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Call the job
        env:
          API_URL: ${{ vars.API_URL }}
          CRON_SECRET: ${{ secrets.CRON_SECRET }}
          SCHEDULE: ${{ github.event.schedule }}
          INPUT_JOB: ${{ github.event.inputs.job }}
        run: |
          case "$SCHEDULE" in
            "7 8 * * 1") JOB=weekly-digest ;;
            "*/30 * * * *") JOB=push-receipts ;;
            "17 3 * * *") JOB=prune-rate-limits ;;
            *) JOB="$INPUT_JOB" ;;
          esac
          curl -fsS --retry 3 --retry-all-errors -X POST \
            -H "X-Cron-Secret: $CRON_SECRET" "$API_URL/internal/cron/$JOB"
```

GitHub may delay scheduled runs by minutes and disables them after 60 days without
repo activity; fine for digests, not for anything time-critical.

**Railway cron service** (runs inside Railway, no GitHub dependency): add a second
service from the same repo with Settings → Cron Schedule `7 8 * * 1` and start command

```bash
curl -fsS -X POST -H "X-Cron-Secret: $CRON_SECRET" "$API_URL/internal/cron/weekly-digest"
```

(one service per schedule; share `CRON_SECRET` with a reference variable
`${{api.CRON_SECRET}}`). Railway cron services must exit when done, which `curl` does.

A failed call exits non-zero, so a missing secret (503) or a wrong one (401) shows up
as a red run, never as a silent no-op.
