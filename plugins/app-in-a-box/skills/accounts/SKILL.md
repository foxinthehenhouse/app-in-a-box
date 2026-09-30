---
name: accounts
description: Phase 3 of App in a Box. Gets the user signed up and logged in to each free service the stack needs, with the least clicking possible. It opens signup pages, waits, then logs in each CLI and connects the MCP servers. It never creates an account on the user's behalf.
---

# Phase 3: Accounts

The only phase where the user does real work. Make it feel like a checklist, not
homework.

## Boundary (say this once, briefly)

> Each service needs *you* to accept its terms and verify your email, so I can't sign
> up for you. I'll open each page. Pick "Continue with GitHub" where it's offered and
> it's one click. Tell me "done" and I'll take it from there.

Never fill in signup forms, solve CAPTCHAs, or create accounts with generated
identities. Everything *after* the account exists is yours to automate.

## Order (dependency order: GitHub first, since the others sign in with it)

Build the list from `appbox.yaml.stack`. Skip anything already logged in; run
`doctor.sh accounts` first to see which.

| # | Service | Signup page | Then run (you) | Needed when |
|---|---|---|---|---|
| 1 | GitHub | https://github.com/signup | `gh auth login --web --scopes repo,workflow,admin:repo_hook` | always |
| 2 | Supabase | https://supabase.com/dashboard/sign-up | `supabase login` | always |
| 3 | Expo | https://expo.dev/signup | `eas login` | always |
| 4 | Railway | https://railway.com/login (GitHub) | `railway login` | `hosting: railway` |
| 5 | PostHog | https://us.posthog.com/signup (pick US or EU; EU for GDPR-heavy apps) | create a **personal API key** with project:write scope, then have the user paste it into `.env` as `POSTHOG_PERSONAL_API_KEY` themselves | `analytics: posthog` |
| 6 | Sentry | https://sentry.io/signup/ | create an **auth token** (org:read, project:write, project:read), then have the user paste it into `.env` as `SENTRY_AUTH_TOKEN` | `errors: sentry` |
| 7 | Linear | https://linear.app/signup | connect the Linear MCP (OAuth) | `tracker: linear` |
| 8 | Anthropic | https://console.anthropic.com | user creates an API key and pastes it into `.env` as `ANTHROPIC_API_KEY` | `ai.enabled: true` |
| 9 | Claude GitHub App | https://github.com/apps/claude | install on the new repo (after phase 5 creates it); `claude setup-token` for `CLAUDE_CODE_OAUTH_TOKEN` | AI PR review |
| 10 | Apple Developer | https://developer.apple.com/programs/enroll/ | **$99/yr + identity check, can take days.** Start now; nothing blocks on it until TestFlight. | iOS release |

### How to run it

1. Open pages in a batch. On macOS use `open <url>`, on Linux `xdg-open <url>`; in
   a headless or cloud session, print the links.
2. Ask "Which have you finished?" (structured, multi-select in Claude Code; a
   numbered list in Codex), listing only the outstanding services.
3. For every finished service, run its login command. Commands that open a browser
   (`gh auth login --web`, `supabase login`, `railway login`) need the user to
   approve in the browser. Tell them which tab.
4. **Pasted secrets.** When a token is needed (PostHog, Sentry, Anthropic), ask the
   user to add it to `.env` themselves (`KEY=value`), not paste it into chat. Chat
   transcripts are stored. Then confirm the name is present with
   `grep -c '^KEY=' .env` (never print the value).
5. Re-run `doctor.sh accounts` until green.

## MCP servers

The plugin ships `.mcp.json` entries for GitHub, Supabase, Railway, PostHog, Sentry,
Linear, Expo and Chrome DevTools. Remote servers use OAuth: tell the user to run
`/mcp` and authenticate each one the stack uses. **A newly authorised MCP server is
only visible after Claude Code restarts.** If you need its tools this session, say
so and fall back to the CLI or REST API. Every provisioning step in phase 5 has a
CLI/API path, so MCP is a convenience, never a blocker. (Codex: `codex mcp login
<server>`, same restart rule. See `KIT/docs/TROUBLESHOOTING.md`.)

The PostHog MCP matters beyond setup: the generated repo's `next` and
`north-star-report` skills read the funnel through it. If the user skips it now,
note it in `appbox.yaml` → `resources.accounts.posthog_mcp: skipped` so `next` can
say "analytics not read" instead of guessing.

## Exit check

`doctor.sh accounts` green for the stack's services. Set `progress.accounts: done`.
Record the handles in `appbox.yaml.resources.accounts` (usernames and org slugs
only).
