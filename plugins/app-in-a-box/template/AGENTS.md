# __APP_NAME__: project context

__ONE_LINER__

**Stage:** Pre-launch MVP. **Owner:** @__OWNER__. Product brief: `docs/product/BRIEF.md`.
Setup record (stack, resources, progress): `appbox.yaml`.

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
maestro test mobile/.maestro/                # E2E flows (per-directory)
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
7. **Mobile-first:** 48px tap targets, theme tokens only, `accessibilityLabel` on
   everything interactive, never meaning by colour alone.
8. **LLM use is fenced.** <!-- appbox:ai-fence: "No LLM calls anywhere." OR "Claude API
   only in backend/services/<module>*." -->
9. **Write endpoints are rate-limited; multi-row writes are atomic.** `Depends(rate_limit(...))`
   on every POST/PATCH/DELETE; more than one row → a Postgres function via `db.rpc()`
   (see `backend/AGENTS.md`).

## Where to look

- `mobile/AGENTS.md`: React Native conventions, tokens, analytics, testIDs
- `backend/AGENTS.md`: FastAPI conventions, auth, feature config, Supabase
- `docs/decision-log.md`: architectural decisions (append-only)
- `docs/runbooks/`: release, rollback, incident, secrets rotation
- `docs/product/`: brief, PRDs, specs

## Agent setup (works in Claude Code and Codex)

Everything agent-facing lives in one neutral place; the per-agent folders are
generated adapters. Edit the source, never the adapter.

| What | Source of truth | Claude Code | Codex |
|---|---|---|---|
| Project instructions | `AGENTS.md` (+ nested) | `CLAUDE.md` → `@AGENTS.md` | reads `AGENTS.md` |
| Skills | `.agents/skills/*/SKILL.md` | `.claude/skills` (symlink), `/name` | native, `$name` |
| Subagents | `.agents/agents/*.md` | `.claude/agents` (symlink) | `.codex/agents/*.toml` (generated) |
| Path rules | `.agents/rules/*.md` | auto-injected by hook | read per the table below |
| Memory | `.agents/memory/` | recall hook + index | read `MEMORY.md` at session start |
| MCP servers | `.mcp.json` | native | `.codex/config.toml` (generated) |
| Hooks | `.claude/hooks/*` scripts | `.claude/settings.json` | `.codex/hooks.json` (trust once) |
| Hard guards | `.githooks/` (no commits on main, no secrets, gates on push) | both | both |

Regenerate adapters after changing a source: re-run the App in a Box renderer, or
see `.agents/README.md`.

### Path rules: read before editing matching files

| Editing | Read first |
|---|---|
| `backend/routers/**`, `backend/models/**`, `mobile/lib/api.ts` | `.agents/rules/api-contract.md` |
| `supabase/migrations/**` | `.agents/rules/db-migrations.md` |
| `mobile/app/**`, `mobile/components/**` | `.agents/rules/mobile-a11y.md`, `.agents/rules/analytics-coverage.md` |
| `mobile/lib/**`, `mobile/eas.json`, `backend/config.py` | `.agents/rules/env-var-wiring.md` |
<!-- appbox:domain-rules: rows for any .agents/rules/<domain>.md enabled from optional/ -->

## How work flows here

Skills are invoked as `/name` in Claude Code and `$name` in Codex; both agents
also pick them up automatically from their descriptions.

1. **Every change has a ticket.** Use the `backlog` skill to pick or file one (GitHub Issues or
   Linear, per `appbox.yaml`). Branch `<type>/<ticket>-<slug>`; the PR references it.
2. **New feature → `feature-discovery` first**, which emits the brief + PRD + tech spec,
   then `build-feature` implements it against the spec.
3. **One unit of work = one branch = one worktree = one PR.** `new-worktree` skill.
   Never commit on `main`; `.githooks/` enforces it for every agent.
4. **Verify before claiming done.** Run the gate and report real output. A test you
   didn't run doesn't count.
5. **PRs are reviewed by the `pr-review` skill** (and the AI review in CI). Squash
   merge; delete the branch. A merged branch is dead, so follow-ups go on a new branch.
6. **Mark real forks with ⚖️.** When you make a call that's arguably the owner's
   (scope cut, tradeoff, risk appetite), say what you chose and the alternative.

**Keeping it moving.** Not sure what to do, or the owner asks "what's next?" → the
`next` skill (it ranks CI, PRs, backlog, rituals and analytics; the session-start
line is its one-line version). Weekly: `north-star-report`. Releases: `ship`.
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

<!-- appbox:voice: from the interview, e.g. "Warm, encouraging, never shaming about money." -->
