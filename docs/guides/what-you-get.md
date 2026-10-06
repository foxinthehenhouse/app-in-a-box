# What's in the generated repo, and why

App in a Box hands you a repo, not a demo. It's built on Expo, FastAPI and Supabase,
with an agent harness around it, and every piece is there because a real production
app needed it. This page is a tour, with the reason for each part.

## The layout

```
mobile/          Expo (React Native) app, TypeScript strict
backend/         FastAPI API: routers/, services/, auth, rate limits, observability
supabase/        Postgres migrations, row-level security, pgTAP tests
design/          tokens.json (from the prototype) and the frozen prototype choices
docs/            product brief and screens, decision log, runbooks, QA
tests/           backend tests, wire-contract test, harness tests
scripts/         dev venv, DB gate, contrast and design checks, OTA rollback
AGENTS.md        instructions every agent reads (CLAUDE.md imports it)
.agents/         skills, subagents, rules, memory, routines, evals (the source of truth)
.claude/ .codex/ generated adapters for Claude Code and Codex
.githooks/       guards that bind every agent and every human
.github/         CI, security scans, AI review, scheduled jobs
```

## Why this stack

The stack is fixed on purpose, so every guard, rule and skill can be specific rather
than generic.

- **Expo** gives you one TypeScript codebase for iPhone and Android, over-the-air
  updates for JavaScript fixes, and EAS to build and submit store binaries in the
  cloud.
- **FastAPI** keeps business logic on the server, typed with Pydantic. The rule in
  `AGENTS.md` is "backend computes, frontend displays", so old app builds in the wild
  don't carry stale logic.
- **Supabase** is Postgres with auth and row-level security, on a free tier. It's
  the single source of truth: no shadow databases, no in-process state.

## The mobile app

Expo Router native tabs (Liquid Glass on iOS 26, Material 3 on Android), email-code
sign-in behind an auth gate, light and dark themes generated from your tokens, and a
component library with a dev-only gallery. Built in and tested: offline-first data
(TanStack Query with queued edits), a push client, deep links through one resolver,
OTA updates with a restart prompt, forms (react-hook-form + zod), i18n, account
deletion and "Download my data". PostHog analytics with typed events and masked
session replay, and Sentry for crashes. A demo mode runs the whole app with no
accounts.

**Why:** these are the pieces that are slow to add later and that app stores ask for
(account deletion is required by both stores).

## The backend and database

FastAPI with Supabase JWT auth, a `/health` endpoint that names every unconfigured
feature instead of failing silently, an error id on every 500, PII-scrubbed Sentry,
rate limits on write endpoints, and an example resource scoped to the caller with
tests that prove the scoping. Migrations ship row-level security on every table, a
profile-on-signup trigger and a free-tier keep-alive.

**Why:** the backend uses the service key, which bypasses row-level security, so the
`user_id` filter in each query is the real guard. The ownership tests fail if anyone
removes it.

## Guards and CI

- **Git hooks** (`.githooks/`): no commits on `main`, no staged `.env`, no
  key-shaped strings, and the gates run before every push.
- **Mobile gates** (`npm run gates`): TypeScript, ESLint (theme tokens only, no hex
  colours), jest with a coverage floor, and guard scripts: every screen fires an
  analytics event, every env var is wired for shipping builds, session replay is
  never unmasked, every screen has a Maestro flow, and the code carries no stock
  design tells.
- **CI**: backend (ruff, pyright, pytest), mobile gates, migrations and RLS tested
  with pgTAP on a throwaway Postgres, gitleaks and CodeQL, workflow lint, harness
  lint, AI PR review (Claude or Codex), and EAS workflows for PR previews, E2E and
  releases.

**Why:** an agent writes code fast and confidently. The guards are what make "it
passed" mean something.

## The agent harness

- `AGENTS.md`, read by both agents, with a map of screens, APIs and tables that a
  test keeps in step with the code.
- 14 skills, including `next` (what to do now), `backlog`, `feature-discovery`,
  `build-feature`, `pr-review`, `land` (drives a PR to merged) and `ship`.
- 10 subagent roles on models chosen per role, and path rules that inject when you
  touch migrations, API contracts or screens.
- Memory in the repo, and a self-learning loop: `reflect` turns corrections into
  memory, and `harness-optimize` proposes harness changes as PRs.

**Why:** a coding agent left alone behaves like a very fast intern. The harness makes
it work like a disciplined team: spec, tests, PR, review, merge.

## What it doesn't include

Payments, an AI feature, social sign-in and push sending are recipes you add when you
need them, not defaults: see
[Add payments, AI, push, offline and social sign-in](add-payments-ai-push-offline-social-sign-in.md).
The kit collects no telemetry: analytics go only to your own PostHog project. The README starts with a small "Built with App in a
Box" badge that you can delete.

## Related

- [Quickstart](../../README.md#quickstart)
- The [`scaffold`](../../plugins/app-in-a-box/skills/scaffold/SKILL.md) skill, which
  renders and shapes the repo, and the
  [`harness`](../../plugins/app-in-a-box/skills/harness/SKILL.md) skill, which turns
  the guards on
- [Production checklist](../../plugins/app-in-a-box/docs/PRODUCTION.md): what's built
  in and what's left to you
- The generated repo's own [AGENTS.md](../../plugins/app-in-a-box/template/AGENTS.md)
  (before rendering)
