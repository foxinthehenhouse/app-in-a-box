---
name: provision
description: Phase 5 of App in a Box. Creates the cloud resources (GitHub repo, Supabase project and its auth email (custom SMTP, Resend recommended), Expo/EAS project, Railway service, PostHog and Sentry projects) idempotently, then wires every secret into .env, GitHub secrets, EAS env and Railway variables. It records IDs in appbox.yaml and never writes secret values to tracked files or chat.
allowed-tools: "Bash(gh:*), Bash(git:*), Bash(supabase:*), Bash(eas:*), Bash(railway:*), Bash(node:*), Bash(npx:*), Bash(openssl:*), Bash(python3:*), Bash(curl:*), Bash(set:*), Bash(grep:*), Bash(touch:*), Bash(cd:*), Read, Write, Edit, Glob, Grep"
---

# Phase 5: Provision

`$KIT` is the plugin root: `appbox.yaml` → `kit_root` if present, else
`${CLAUDE_PLUGIN_ROOT}` (Claude Code) or the folder two levels above this file (Codex /
pasted prompt).

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
without the flag, and phase 7 (the doctor's Full mode) adds branch protection on
GitHub once CI has reported. Record `resources.github.repo`.

**If the push is refused by `bash-safety`** ("pushing to main/master directly"): that
is the generated repo's own Claude Code hook. It loads from `.claude/settings.json` at
session start, so a session that began before phase 4 doesn't run it, but a RESUMED
session does, and the hook has no bootstrap flag. Don't edit or disable the hook.
Hand the owner the one command to run in their own terminal, from the project folder:

```
APPBOX_BOOTSTRAP=1 git push -u origin main:main
```

Wait for "done", then verify with `git ls-remote --heads origin main` (one line
means it landed) and carry on with the setup branch. Symptom and fix also live in
`$KIT/docs/TROUBLESHOOTING.md`.

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

7. **Auth email (custom SMTP).** Supabase, not the API, sends the sign-in code, and
   its built-in mailer allows only a couple of emails an hour (new projects can't
   even edit their email templates without custom SMTP). That's fine for you testing
   the prototype and fails the first day real users sign in, so ask now:

   > Sign-in emails need a mail service before real users arrive. **Resend
   > (recommended)**: free for 100 emails a day, about five minutes. **Another SMTP
   > provider** you already use (Postmark, SES, SendGrid...). Or **later**: fine for a
   > prototype, but `/health` in production says email isn't working until it's done.

   Either way the owner needs:
   - A **Supabase personal access token** (supabase.com/dashboard/account/tokens),
     pasted into `.env` as `SUPABASE_ACCESS_TOKEN` by them. It's for provisioning
     only; it never goes to Railway, EAS or GitHub.
   - **Resend:** sign up at https://resend.com/signup, add and verify the app's
     domain (Domains → DNS records; until it's verified Resend only delivers to the
     account's own address), then create an API key with sending access and paste it
     into `.env` as `SMTP_PASS`. **Other SMTP:** the provider's host, port and username
     (they can tell you those; none is secret), and its password pasted into `.env`
     as `SMTP_PASS`.

   Confirm both names with `grep -c '^SMTP_PASS=.' .env` and
   `grep -c '^SUPABASE_ACCESS_TOKEN=.' .env` (never print a value). Then point the
   project at it. The script reads both secrets from the environment, sends the
   Management API `PATCH /v1/projects/<ref>/config/auth` (`smtp_host`, `smtp_port`,
   `smtp_user`, `smtp_pass`, `smtp_admin_email`, `smtp_sender_name`), and prints only
   `AUTH_SMTP_HOST=<host>`, which `env_set.py` records:
   ```
   set -a; . ./.env; set +a; python3 "$KIT/scripts/supabase_smtp.py" --ref "<ref>" --resend --sender-email "no-reply@<verified domain>" --sender-name "<App name>" | python3 "$KIT/scripts/env_set.py" .env
   ```
   Other SMTP: replace `--resend` with `--host <host> --port <465|587> --user <user>`.
   Add `--dry-run` first if you want to see the request; the password and token show
   as `***`. Never pass a secret as an argument, `curl -d` it, or `echo` it: the
   script exists so neither value touches a command line or the transcript.

   `AUTH_SMTP_HOST` (the host name, not a secret) goes to Railway in step 6. It's how
   the API knows email works: with `APP_ENV=production` and no `AUTH_SMTP_HOST`,
   `/health` lists "email sign-in (custom SMTP)" under `features_unavailable`. The
   SMTP password lives only in Supabase and `.env`.

   Supabase starts custom SMTP at 30 auth emails an hour. Resend's free 100 a day fits
   under that, so leave it; on a bigger plan add `--rate-limit <emails per hour>`.
   Then send yourself a code from the app to check the sender and the domain.

   Local development needs none of this: `supabase start` catches every email in its
   own inbox (Mailpit, on the port `supabase status` names). To send real mail from
   the local stack, add `[auth.email.smtp]` to `supabase/config.toml` with
   `enabled = true`, `host`, `port`, `user`, `admin_email`, `sender_name`, and
   `pass = "env(SMTP_PASS)"` so the key stays in `.env`.

   **Later:** record `resources.supabase.smtp: deferred` and leave `AUTH_SMTP_HOST`
   unset; production `/health` keeps saying so until it's done.

Record `resources.supabase.{ref,url,region,smtp}` (`smtp`: the host, or `deferred`).

## 3. Sentry (two projects: `<slug>-api`, `<slug>-app`)

**Skip if `stack.errors: none`.** Monitoring stays a no-op without a DSN; leave
`SENTRY_DSN` / `EXPO_PUBLIC_SENTRY_DSN` out of `.env` and EAS, and set
`upload_sentry_sourcemaps: false` on every `type: update` job in
`mobile/.eas/workflows/` (there's nowhere to upload to; `tests/test_eas_workflows.py`
reads `stack.errors` and expects exactly that).

The Sentry MCP (`create_project`, `find_dsns`) works. The REST fallback, with
`SENTRY_AUTH_TOKEN` from `.env`:
- Org/team: `GET https://sentry.io/api/0/organizations/` → `GET .../organizations/<org>/teams/`.
- Create: `POST https://sentry.io/api/0/teams/<org>/<team>/projects/` with
  `{"name":"<slug>-api","platform":"python-fastapi"}` and
  `{"name":"<slug>-app","platform":"react-native"}`.
- DSN: `GET https://sentry.io/api/0/projects/<org>/<project>/keys/` → `dsn.public`.
Write `SENTRY_DSN` (api) and `EXPO_PUBLIC_SENTRY_DSN` (app) to `.env`. DSNs are
not secret, but keep them in env for per-environment swaps.

Source maps: every OTA job in the EAS workflows uploads its own and **fails** if it
can't, so an OTA crash is never unreadable. After step 5's `eas init`, give both EAS
environments the upload credentials (the token as `sensitive`, never printed):

```
set -a; . ../.env; set +a; for env in preview production; do
  eas env:create --environment "$env" --name SENTRY_AUTH_TOKEN --value "$SENTRY_AUTH_TOKEN" --visibility sensitive --non-interactive --force
  eas env:create --environment "$env" --name SENTRY_ORG --value "<org slug>" --visibility plaintext --non-interactive --force
  eas env:create --environment "$env" --name SENTRY_PROJECT --value "<slug>-app" --visibility plaintext --non-interactive --force
done
```

## 4. PostHog

**Skip if `stack.analytics: none`.** Analytics stays a no-op without a key; leave
the `*POSTHOG*` variables out of `.env` and EAS.

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

EAS Workflows (`mobile/.eas/workflows/`) need no `EXPO_TOKEN`: the owner connects
the expo.dev GitHub app to the repo (base directory `mobile`) once. Store submission
for `release.yml` is set up per store, only when the owner is ready to ship there:

- **iOS (owner):** create the app in App Store Connect (needs a paid Apple Developer
  account), then run `cd mobile && eas credentials -p ios` → App Store Connect →
  "Set up your project to use an API Key for EAS Submit". Ask for the app's
  **Apple ID** (App Store Connect → the app → General → App Information) and write
  it as a number to `mobile/eas.json` → `submit.production.ios.ascAppId` and to
  `appbox.yaml` → `ids.asc_app_id`. Without it every TestFlight submit fails
  non-interactively. `tests/test_eas_workflows.py` checks it's an Apple ID, not a
  bundle id, and that no key file path is committed.
- **Android (owner):** Google Play requires the first upload by hand (Play Console →
  the app → Internal testing → upload the first production `.aab`). Then
  `eas credentials -p android` → upload a Google service account key. Never put the
  key file in the repo.

## 6. Backend hosting (Railway)

Use the Railway MCP (`create-project`, `create-service`, `set-variables`,
`generate-domain`, `connect-service-source`) when connected. CLI fallback:

```
railway init --name "<slug>"
```

Create a service for the API connected to the GitHub repo (auto-deploy on push to
`main`), set variables from `.env` (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`SUPABASE_ANON_KEY`, `SENTRY_DSN`, `APP_ENV=production`, `AUTH_SMTP_HOST` once step
2.7 has run, and `ANTHROPIC_API_KEY` if AI is enabled), and generate a domain. Never
set `SMTP_PASS` or `SUPABASE_ACCESS_TOKEN` on Railway: the API needs neither. Write
that domain to `.env` as `API_URL` and `EXPO_PUBLIC_API_URL`, then go back to step 5
for the EAS var. `railway.json` from the template sets the start command and `/health`
healthcheck.

Fly.io or Render instead of Railway: same variables and the same `/health` healthcheck;
use that platform's CLI/dashboard in place of the Railway steps above.

## 7. GitHub secrets and variables

```
gh secret set SUPABASE_URL --body "$SUPABASE_URL"
```

(inside a `set -a; . ./.env; set +a;` prefix). Set `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY` (keep-alive workflow) and
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

## Turning a declined service on later

Set it in `appbox.yaml` (`stack.analytics: posthog`, `stack.errors: sentry` or
`stack.tracker: linear`), re-run `python3 "$KIT/scripts/render.py" --target .
--adapters-only` (it restores that service's MCP server in `.mcp.json` and
`.codex/config.toml`), then do its row in the accounts phase and its step above. The
app's calls were no-ops all along, so no app code changes.

## Exit check

- Every `appbox.yaml.resources` entry resolves (list calls succeed).
- `git status --porcelain` shows no `.env`.
- `node mobile/scripts/check-eas-shipping-env.js` passes (once `mobile/` exists).
- `curl -fsS "$API_URL/health"` returns 200 (once deployed), and its
  `features_unavailable` doesn't name "email sign-in (custom SMTP)" unless the owner
  chose to defer it.

Set `progress.provision: done`.
