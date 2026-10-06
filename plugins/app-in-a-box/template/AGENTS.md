# __APP_NAME__: project context

__ONE_LINER__

**Stage:** Pre-launch MVP. **Owner:** @__OWNER__. Product brief: `docs/product/BRIEF.md`.
Setup record (stack, resources, progress): `appbox.yaml`.

## Product

<!-- appbox:product: scaffold fills from BRIEF.md + VALIDATION.md: who it's for, their
problem, core loop, positioning, north-star metric, top riskiest assumption (≤ 10 lines). -->

## Stack

Expo / React Native (TypeScript strict) · FastAPI (Python 3.12, :8000) · Supabase
(Postgres + Auth + RLS) · Railway (API) · EAS (builds, OTA) · PostHog (analytics) ·
Sentry (errors) · GitHub Actions (CI + AI review).

## Commands

```bash
scripts/dev-venv.sh python -m pytest -q     # backend tests (py3.12 venv, shared across worktrees)
./run.sh                                     # API on :8000 with reload
cd mobile && npm run gates                   # tsc + eslint + guard scripts + jest (pre-push gate)
cd mobile && npx expo start                  # app in Expo Go / dev client
maestro test mobile/.maestro/                # E2E flows (docs/qa/MAESTRO.md)
```

## Critical rules (non-negotiable)

<!-- appbox:critical-rules: the scaffold phase adds domain rules from BRIEF.md here, e.g.
     "Money amounts are integers in minor units, never floats." -->
1. **Backend computes, frontend displays.** No business logic in React Native.
2. **Supabase is the single source of truth.** No shadow databases, no in-process state
   (the API runs multiple workers; module-level dicts are per-process).
3. **Scope every query by the caller's user id.** The backend uses the service key,
   which bypasses RLS, so the `.eq("user_id", user.id)` in your query is the only guard.
4. **Type safety.** Pydantic at the backend boundary, TypeScript strict, no `any`.
   Wire shapes are mirrored by hand: `*Wire` types + adapters in `mobile/lib/api.ts`.
5. **Additive wire changes only.** Old app builds stay in the wild for weeks. Never
   rename, retype or remove a response field in place.
6. **Every screen fires an analytics event; every mutation fires success AND failure.**
7. **Mobile-first. Read `DESIGN.md` before any UI work**; change tokens via the design flow,
   never by hand. 48px taps, `accessibilityLabel` on every control, never colour alone.
8. **LLM use is fenced.** <!-- appbox:ai-fence: "No LLM calls anywhere." OR "Claude API
   only in backend/services/<module>*." -->
9. **Write endpoints are rate-limited; multi-row writes are atomic.** `Depends(rate_limit(...))`
   on every POST/PATCH/DELETE; more than one row → a Postgres function via `db.rpc()`
   (see `backend/AGENTS.md`).

## Where to look

- `mobile/AGENTS.md`: React Native conventions, tokens, analytics, testIDs
- `backend/AGENTS.md`: FastAPI conventions, auth, feature config, Supabase
- `docs/decision-log.md`: architectural decisions (append-only)
- `docs/runbooks/`: release, rollback, incident, secrets rotation, backups; `COST.md`: running costs + spend caps
- `docs/product/`: brief, PRDs, specs

## Where things live

**Update the row in the same PR as the code:** `tests/harness/test_agents_md_current.py`
fails CI when a screen, router, service or table is missing here.

| Area | Screens (`mobile/`) | API (`backend/`) | Logic (`backend/`) | Tables |
|---|---|---|---|---|
| Sign-in; Home (the core loop) | `app/(auth)/sign-in.tsx`; `app/(app)/index.tsx` | (Supabase Auth) | | |
| Profile, settings, account | `app/(app)/settings.tsx`, `app/edit-name.tsx`, `app/delete-account.tsx` | `routers/me.py` | | `profiles` |
| Data export | | `routers/export.py` | | |
| Push notifications | | `routers/push.py` | `services/push_service.py` | `push_tokens`, `push_tickets` |
| Scheduled jobs, rate limits | | `routers/internal.py` | `services/jobs_service.py` | `job_runs`, `rate_limits`, `keep_alive` |
| Dev only | `app/gallery.tsx` | | | |

## Agent setup (works in Claude Code and Codex)

Everything agent-facing lives in `.agents/` (skills, subagents, rules, memory);
`.claude/` and `.codex/` are generated adapters, so edit the source, never the adapter.
The source → adapter table and how to regenerate: `.agents/README.md`.

### Path rules: read before editing matching files

| Editing | Read first |
|---|---|
| `backend/routers/**`, `mobile/lib/api.ts` | `.agents/rules/api-contract.md` |
| `supabase/migrations/**` | `.agents/rules/db-migrations.md` |
| `mobile/app/**`, `mobile/components/**`, `mobile/lib/analytics.ts` | `.agents/rules/mobile-a11y.md`, `.agents/rules/analytics-coverage.md` |
| `mobile/lib/**`, `mobile/app.json`, `mobile/eas.json`, `backend/config.py`, `backend/main.py` | `.agents/rules/env-var-wiring.md` |
| `docs/product/**`, `mobile/app/**`, `mobile/locales/**`, `mobile/components/**`, and any product call anywhere | `.agents/rules/product-judgement.md` |
<!-- appbox:domain-rules: rows for any .agents/rules/<domain>.md enabled from optional/ -->

## How work flows here

Skills are invoked as `/name` in Claude Code and `$name` in Codex; both agents also pick them up from their descriptions.

1. **Every change has a ticket.** Use the `backlog` skill to pick or file one (Linear or
   GitHub Issues, per `appbox.yaml`). Branch `<type>/<ticket>-<slug>`; the PR references
   it, and the `ticket` CI check enforces that. **File sub-tasks and follow-ups the
   moment you find them** (sub-issues of the current ticket, or new related tickets),
   never "later" in chat.
2. **New feature → `feature-discovery` first** (brief + PRD + tech spec), then `build-feature` builds it against the spec.
3. **One unit of work = one branch = one worktree = one PR.** `new-worktree` skill.
   Never commit on `main`; `.githooks/` enforces it for every agent.
4. **Verify before claiming done.** Run the gate and report real output. A test you
   didn't run doesn't count.
5. **`pr-review` reviews each PR; the `land` skill drives it to merged** (CI, every
   thread, re-review per push). Merging without asking needs `appbox.yaml` →
   `policy.auto_merge_low_risk: true` (default `false`) AND a ✅ low-risk verdict with
   green CI; otherwise the owner merges. Squash merge, delete the branch; follow-ups get a new one.
6. **Ask, don't decide, on product calls.** Scope, what users see, money, positioning,
   data and priorities belong to the owner: ask with a structured question
   (recommended option first) per `.agents/rules/product-judgement.md`. Calls you make
   within authority you already have get a ⚖️ and the alternative, so they can be
   overruled.

**Keeping it moving.** Not sure what to do, or the owner asks "what's next?" → the
`next` skill (it ranks CI, PRs, backlog, rituals and analytics; the session-start
line is its one-line version). Weekly: `north-star-report`. Monthly: `market-watch`
(re-checks competitors against `docs/product/VALIDATION.md`). Releases: `ship`.
Scheduling rituals: `routines`. Subagents run on routed models (Opus judges, Sonnet
builds, Haiku sweeps, `chair` on Fable rules on irreversible calls): don't override
`model:` without a reason. Claude Code also has opt-in Workflows
(`.claude/workflows/`) for thorough `build-feature` / `pr-review` runs: several times
the tokens, so only when the owner asks. Skill evals: `.agents/evals/`.

## Memory

`.agents/memory/` is the project's long-term memory, git-tracked so every agent and
machine shares it. `MEMORY.md` is the index (≤ 45 lines); **read it at session
start** and open the notes that apply. Write a note (via the `reflect` skill) only for
something **non-obvious that will still be true in 30 days**, never for code patterns
or paths.

**Self-learning loop:** hooks capture every tool call and seed a pending reflection
after substantive sessions → `reflect` (every ~10d) turns corrections into notes →
`pattern-extractor.py` + `skill-lifecycle.py` + `spend_ledger.py` feed `harness-optimize`
(every ~7d), which proposes harness changes as a PR and never removes a component
protected in `.claude/harness/manifest.json`. The session-start healthcheck flags drift
and says which ritual is overdue; `harness-check` gives the full report.

## Review guidelines

Used by the `pr-review` skill, Claude's CI review and Codex code review alike.
- Blocker: missing user-id scoping, a secret in code, an in-place wire change, a test
  weakened to pass, a new env var not wired for shipping builds.
- Major: a mutation without success+failure analytics, a screen without a view event,
  a missing accessibility label, a hex literal or raw size in a screen.
- Don't flag style that the linters already enforce.

## Voice (copy that ships to users)

<!-- appbox:voice: from the brief and the copy tone frozen in SCREENS.md, e.g. "Warm, encouraging, never shaming about money." -->
