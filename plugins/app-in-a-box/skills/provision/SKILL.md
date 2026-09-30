---
name: provision
description: Phase 5 of App in a Box. Creates the cloud resources (GitHub repo, Supabase project, Expo/EAS project, Railway service, PostHog and Sentry projects) idempotently, then wires every secret into .env, GitHub secrets, EAS env and Railway variables. It records IDs in appbox.yaml and never writes secret values to tracked files or chat.
---

# Phase 5: Provision

## Ground rules

- **Check before create.** For every resource, list first and reuse a match by
  name. Record IDs/URLs in `appbox.yaml.resources`.
- **Secrets flow through the shell, not through you.** Write generated secrets
  straight to `.env` with shell redirection. Load them with
  `set -a; . ./.env; set +a` in the same command that uses them. Never `echo`,
  `cat` or print a secret value, and never put one in a commit, `appbox.yaml`,
  or chat.
- **CLIs drift.** Before the first use of each CLI subcommand, run
  `<cli> <subcommand> --help` and adapt flags. The commands below are the
  intended shape, not gospel.
- **MCP if available, CLI otherwise.** The Supabase, Railway, GitHub, PostHog and
  Sentry MCP servers can do most of this. If they're not connected this session,
  the CLI/REST path below always works.
- Ask before anything that **costs money**: a Railway plan upgrade, a Supabase
  compute add-on, or an Apple enrolment. Nothing below costs money on free tiers,
  except that Railway needs its trial/hobby plan.

## 0. `.env` and `.gitignore` first

```
touch .env && grep -qxF '.env' .gitignore 2>/dev/null || printf '.env\n.env.*\n!.env.example\n' >> .gitignore
```

## 1. GitHub repo

```
gh repo view "<owner>/<slug>" >/dev/null 2>&1 || gh repo create "<owner>/<slug>" --private --source=. --remote=origin
```

Then push the bootstrap commit phase 4 made to `main`, and the setup branch you're on:

```
APPBOX_BOOTSTRAP=1 git push -u origin main:main
```

```
git push -u origin chore/appbox-setup
```

The first is the only direct push to `main` ever. `.githooks/pre-push` refuses it
without the flag, and phase 6 adds branch protection on GitHub. Record
`resources.github.repo`.

## 2. Supabase

1. Org: `supabase orgs list -o json` → pick the user's org (ask if more than one).
2. Existing project? `supabase projects list -o json` → match on name `<slug>`.
3. Create if missing, with the password generated straight into `.env`:
   ```
   grep -q '^SUPABASE_DB_PASSWORD=' .env || printf 'SUPABASE_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> .env
   ```
   ```
   set -a; . ./.env; set +a; supabase projects create "<slug>" --org-id "<org>" --db-password "$SUPABASE_DB_PASSWORD" --region "<region nearest the user>" -o json
   ```
4. Wait for `ACTIVE_HEALTHY` (poll `supabase projects list`), then get the keys
   into `.env` without printing them. The publishable/anon key is safe for the
   client; the secret/service-role key is server-only:
   ```
   supabase projects api-keys --project-ref "<ref>" -o json | python3 -c 'import json,sys; k={x["name"]:x["api_key"] for x in json.load(sys.stdin)}; print("SUPABASE_URL=https://<ref>.supabase.co"); print("SUPABASE_ANON_KEY="+k["anon"]); print("SUPABASE_SERVICE_ROLE_KEY="+k["service_role"])' | python3 "$KIT/scripts/env_set.py" .env
   ```
   The keys flow through the pipe into `.env`; `env_set.py` prints only their names.
   Never write keys to a temp file or print them. The generated repo's bash-safety
   hook blocks any command that reads `.env` back out. If the CLI names the keys
   differently (newer projects return `publishable` / `secret`), map those names.
5. Link and push the migrations phase 4 wrote:
   `supabase link --project-ref "<ref>" -p "$SUPABASE_DB_PASSWORD"` →
   `supabase db push`.
6. Auth config: set Site URL and redirect allow-list to `<slug>://**` and
   `exp://**` (the Supabase MCP, or Management API
   `PATCH /v1/projects/<ref>/config/auth`). Email OTP is on by default. Apple and
   Google providers need console setup; see `$KIT/docs/SOCIAL_AUTH.md`. Defer
   them if the user wants to move fast. Email OTP is enough to ship a prototype.

Record `resources.supabase.{ref,url,region}`.

## 3. Sentry (two projects: `<slug>-api`, `<slug>-app`)

The Sentry MCP (`create_project`, `find_dsns`) works. The REST fallback, with
`SENTRY_AUTH_TOKEN` from `.env`:
- Org/team: `GET https://sentry.io/api/0/organizations/` → `GET .../organizations/<org>/teams/`.
- Create: `POST https://sentry.io/api/0/teams/<org>/<team>/projects/` with
  `{"name":"<slug>-api","platform":"python-fastapi"}` and
  `{"name":"<slug>-app","platform":"react-native"}`.
- DSN: `GET https://sentry.io/api/0/projects/<org>/<project>/keys/` → `dsn.public`.
Write `SENTRY_DSN` (api) and `EXPO_PUBLIC_SENTRY_DSN` (app) to `.env`. DSNs are
not secret, but keep them in env for per-environment swaps.

## 4. PostHog

Use the PostHog MCP if connected. Otherwise use the REST API with
`POSTHOG_PERSONAL_API_KEY`: list projects, create `<App name>` if missing, and
read its `api_token`. That token is the **public** project key; write it as
`EXPO_PUBLIC_POSTHOG_API_KEY` and `POSTHOG_API_KEY`, plus `EXPO_PUBLIC_POSTHOG_HOST`
(`https://us.i.posthog.com` or `https://eu.i.posthog.com`). Check the current
endpoint path in PostHog's API docs before calling it.

## 5. Expo / EAS

```
cd mobile && eas init --non-interactive --force
```

This writes `extra.eas.projectId` into app config. Then push every
`EXPO_PUBLIC_*` value to EAS for `preview` and `production`:

```
set -a; . ../.env; set +a; for env in preview production; do eas env:create --environment "$env" --name EXPO_PUBLIC_SUPABASE_URL --value "$SUPABASE_URL" --visibility plaintext --non-interactive --force; done
```

Repeat for `EXPO_PUBLIC_SUPABASE_ANON_KEY` (`sensitive`),
`EXPO_PUBLIC_POSTHOG_API_KEY`, `EXPO_PUBLIC_POSTHOG_HOST`,
`EXPO_PUBLIC_SENTRY_DSN` and `EXPO_PUBLIC_API_URL` (after step 6). Then run
`node mobile/scripts/check-eas-shipping-env.js`. It fails if code reads an
`EXPO_PUBLIC_*` that shipping builds won't have.

## 6. Backend hosting (Railway)

Use the Railway MCP (`create-project`, `create-service`, `set-variables`,
`generate-domain`, `connect-service-source`) when connected. CLI fallback:

```
railway init --name "<slug>"
```

Create a service for the API connected to the GitHub repo (auto-deploy on push to
`main`), set variables from `.env` (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`SUPABASE_ANON_KEY`, `SENTRY_DSN`, `APP_ENV=production`, and
`ANTHROPIC_API_KEY` if AI is enabled), and generate a domain. Write that domain to
`.env` as `API_URL` and `EXPO_PUBLIC_API_URL`, then go back to step 5 for the EAS
var. `railway.json` from the template sets the start command and `/health`
healthcheck.

Fly.io or Render instead of Railway: same variables and the same `/health` healthcheck;
use that platform's CLI/dashboard in place of the Railway steps above.

## 7. GitHub secrets and variables

```
gh secret set SUPABASE_URL --body "$SUPABASE_URL"
```

(inside a `set -a; . ./.env; set +a;` prefix). Set `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY` (keep-alive workflow), `EXPO_TOKEN` (the user creates
it at expo.dev → Access tokens and adds it to `.env`) and
`CLAUDE_CODE_OAUTH_TOKEN` (the user runs `claude setup-token` and adds it to
`.env`). Then set `gh variable set ENABLE_CLAUDE_REVIEW --body true`.

Scheduled jobs (`cron.yml` stays off until `API_URL` is set): generate the secret
straight into `.env`, then give it to both Railway and GitHub:

```
grep -q '^CRON_SECRET=.\+' .env || printf 'CRON_SECRET=%s\n' "$(openssl rand -hex 32)" >> .env
```

```
set -a; . ./.env; set +a; gh secret set CRON_SECRET --body "$CRON_SECRET" && gh variable set API_URL --body "$API_URL"
```

Set `CRON_SECRET` on the Railway API service too (step 6's variables). Until both
sides have it, `/internal/cron/*` answers 503 naming the missing feature.

## 8. Write `.env.example`

Same keys as `.env`, empty values, grouped by service with a comment naming where
each is created. **This file is tracked.** Check it contains no values before
committing: `grep -E '=.+' .env.example` must print nothing. Commit it and the updated
`appbox.yaml` (resource IDs, never values) on `chore/appbox-setup`, not on `main`.

## Exit check

- Every `appbox.yaml.resources` entry resolves (list calls succeed).
- `git status --porcelain` shows no `.env`.
- `node mobile/scripts/check-eas-shipping-env.js` passes (once `mobile/` exists).
- `curl -fsS "$API_URL/health"` returns 200 (once deployed).

Set `progress.provision: done`.
