# Release runbook

How a change gets from `main` to users, and how the scheduled jobs are wired. Owner
steps are marked **(owner)**: an agent can't press store buttons or set deploy config.

## What ships where

| Layer | Ships by | Rollback |
|---|---|---|
| Backend (FastAPI) | Railway auto-deploys `main` | [rollback.md](rollback.md#backend) |
| Database | `supabase db push` **(owner)** | [rollback.md](rollback.md#database) |
| JS / assets | OTA via EAS Update (`release.yml`, native unchanged) | [rollback.md](rollback.md#ota) |
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
4. **Store steps (owner):** in App Store Connect add the build to review (use phased
   release); in Play Console promote internal → production with a staged rollout.

Why this order: old app builds stay installed for weeks, so the API must accept what
they send (additive wire changes only), and the schema must accept what both API
versions write.

## Before a store submission

- [ ] The App in a Box production checklist (`docs/PRODUCTION.md` in the kit) is green:
      privacy manifest, nutrition label, account deletion reachable in-app, a demo
      account in the App Review notes.
- [ ] Sign-in email goes through custom SMTP: production `/health` doesn't list
      "email sign-in (custom SMTP)", and a code sent to a fresh address arrives from
      your domain within a minute. Supabase's built-in mailer allows a couple of
      emails an hour, so App Review (and your first users) can't sign in without it.
- [ ] `version` bumped in `mobile/app.json` for a native release (build numbers are
      remote-managed: `appVersionSource: remote`).
- [ ] Sentry release = git sha (Railway sets `RAILWAY_GIT_COMMIT_SHA`; the app's
      Sentry plugin uploads source maps during EAS Build).

## PR previews

`mobile/.eas/workflows/pr-preview.yml` runs on every PR: unchanged native → OTA to branch
`pr-<number>` (open it from the preview build's update picker / dev client); changed
native → a fresh preview build. Railway PR environments are optional (Railway →
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
