# Secrets rotation runbook

Rotate on a schedule (every 6-12 months), when someone with access leaves, and
immediately if a secret may have leaked (committed, pasted, logged). Secrets never live
in git: `.env` is dev-only and the pre-commit hook refuses key-shaped strings.

General rule: **add the new secret, deploy, verify, then revoke the old one.** Where a
system supports two active keys, that gives zero downtime.

| Secret | Lives in | Rotate | Blast radius if leaked |
|---|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SECRET_KEY` | Railway | Supabase → Project Settings → API Keys: create a new secret key (`sb_secret_...`), set it on Railway, redeploy, verify `/health?deep=1`, then delete the old key. Legacy JWT-based service keys can only rotate by rotating the JWT secret, which also signs out every user: migrate to the new API keys first. | **Total**: bypasses RLS on every table |
| Supabase JWT signing key | Supabase | Auth → JWT Keys: create a standby key, rotate. The API verifies against JWKS and picks up the new key automatically; existing sessions stay valid until expiry. | Forged sessions |
| `CRON_SECRET` | Railway + GitHub secret (or Railway cron service) | `openssl rand -hex 32`; set on Railway AND the scheduler at the same time (one missed run is fine, jobs are idempotent). | Anyone can trigger jobs (spam digests) |
| `EXPO_ACCESS_TOKEN` | Railway | expo.dev → Account → Access tokens: create, set, redeploy, revoke old. | Send pushes as your app (with enhanced security on) |
| `EXPO_TOKEN` (CI) | GitHub secret | expo.dev → Access tokens. | Builds/updates published as you: **rotate immediately** |
| `SENTRY_DSN` | Railway, EAS env | Sentry → Client Keys: add key, switch, disable old. DSNs are semi-public (they ship in the app); rotate only if abused. | Junk events |
| `SENTRY_AUTH_TOKEN` | EAS env (source maps) | Sentry → Auth Tokens. | Read your Sentry data |
| `ANTHROPIC_API_KEY` (if AI enabled) | Railway | console.anthropic.com → create key, set, redeploy, delete old. | Spend on your account |
| RevenueCat webhook secret (if payments) | Railway + RevenueCat | RevenueCat → Integrations → Webhooks: change the Authorization header value, then Railway. | Forged entitlement grants |
| Store credentials (ASC API key, Play service account) | EAS credentials | `eas credentials` → remove + re-add. | Ship binaries as you |

## Commands

```bash
railway variables --set "NAME=value"                  # Railway (triggers a redeploy)
gh secret set NAME --body "value"                     # GitHub Actions
eas env:create --name NAME --value "value" --environment production --visibility secret --force
```

## If a secret was committed

1. Rotate it first (above). Removing it from git history does not un-leak it.
2. Then purge history if the repo is public (`git filter-repo`), and check the
   provider's audit log for use during the exposure window.
3. Add the pattern to the pre-commit scan if it wasn't caught.
