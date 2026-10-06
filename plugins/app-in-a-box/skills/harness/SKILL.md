---
name: harness
description: Phase 6 of App in a Box. Switches on the agent harness the scaffold wrote. It covers GitHub branch protection, labels and the AI review workflow, git hooks, Claude Code and Codex adapters (trust, hooks, MCP auth), and a smoke test that every guard actually fires. Use after provisioning, or to repair a harness that drifted.
allowed-tools: "Bash(git:*), Bash(gh:*), Bash(python3:*), Bash(bash:*), Read, Glob, Grep"
---

# Phase 6: Harness

`$KIT` is the plugin root: `appbox.yaml` → `kit_root` if present, else
`${CLAUDE_PLUGIN_ROOT}` (Claude Code) or the folder two levels above this file (Codex /
pasted prompt).

The files already exist (the renderer wrote them in phase 4). This phase turns them
on and **proves each one works**. A guard that can't fail reads as a guard that
passes.

## 1. What was installed (tell the user in 4 lines, not a table dump)

- `AGENTS.md` (+ `mobile/`, `backend/`) is the instructions every agent reads.
  `CLAUDE.md` files import it.
- `.agents/`: 15 skills (backlog, next, feature-discovery, build-feature, pr-review,
  land, ship, incident, new-worktree, reflect, north-star-report, market-watch, routines,
  harness-check, harness-optimize), 10 subagent roles with routed models, path rules, a memory
  vault and skill evals. Claude Code also gets opt-in Workflows in `.claude/workflows/`.
- Adapters: `.claude/` (settings, hooks, symlinks) and `.codex/` (agents, MCP config,
  hooks), both generated from `.agents/`.
- `.githooks/` + `.github/workflows/` are the hard guards that bind every agent and
  human.

## 2. Git + GitHub

```
git config core.hooksPath .githooks
```

Branch protection on `main` (require PR + the CI checks). The required contexts are
the **job ids** from the workflows, every one of which runs on every PR: `python` and
`mobile` (`ci.yml`), `migrations-rls` (`db.yml`), `gitleaks` (`security.yml`),
`ticket` (`ticket.yml`) and `pr-title` (`pr-title.yml`). Six ids; the marker below,
the `gh` command and the kit selftest all carry the same six, so a seventh job joins
all four places or none.
Never require a job that can be skipped by a path filter or an `if:` condition
(`codeql`, `review`), or PRs wait forever on a check that never reports. The kit
selftest fails if this list names a job that doesn't exist.

<!-- required-checks: python mobile migrations-rls gitleaks ticket pr-title -->

```
gh api -X PUT "repos/<owner>/<slug>/branches/main/protection" -F "required_status_checks[strict]=true" -F "required_status_checks[contexts][]=python" -F "required_status_checks[contexts][]=mobile" -F "required_status_checks[contexts][]=migrations-rls" -F "required_status_checks[contexts][]=gitleaks" -F "required_status_checks[contexts][]=ticket" -F "required_status_checks[contexts][]=pr-title" -F "enforce_admins=false" -F "required_pull_request_reviews=null" -F "restrictions=null"
```

GitHub only offers checks it has seen, so this call is **deferred to phase 7**: the
doctor's Full mode runs it after the first PR's CI has reported, then verifies with
`gh api "repos/<owner>/<slug>/branches/main/protection" --jq '.required_status_checks.contexts'`
(all six ids listed). This phase's exit check only needs the hooks on and the
command ready. Private repos on a free GitHub plan can't use branch protection: if
the call returns 403, record `resources.github.protection: unavailable (plan)` in
`appbox.yaml`, say so, and rely on the git hooks.

Labels for the backlog skill:

```
for l in feat fix chore p0 p1 p2 ready; do gh label create "$l" --force >/dev/null; done
```

AI review in CI, by the user's agent:
- **Claude Code:** install https://github.com/apps/claude on the repo, run
  `claude setup-token`, put the token in `.env` as `CLAUDE_CODE_OAUTH_TOKEN`, then
  `gh secret set CLAUDE_CODE_OAUTH_TOKEN` (from `.env`) and
  `gh variable set ENABLE_CLAUDE_REVIEW --body true`.
- **Codex:** enable Codex code review for the repo in Codex's settings (it follows
  the "Review guidelines" section of `AGENTS.md`). Leave `ENABLE_CLAUDE_REVIEW` unset.
- Both is fine. They review independently.

## 3. Agent adapters

- **Claude Code:** nothing to trust. Hooks load from `.claude/settings.json` on
  the next session. `/mcp` → authenticate `supabase`, `posthog`, `sentry` (and
  `linear` if used). Set `GITHUB_PAT` in the shell env for the GitHub MCP, or rely
  on `gh`.
- **Codex:** mark the project trusted (Codex asks on first launch in the folder; the
  project `.codex/config.toml` is ignored until then). Approve each hook in
  `.codex/hooks.json` once when prompted. Run `codex mcp login <server>` for each
  OAuth server.
- **Symlinks.** If `.claude/skills` is a copy rather than a symlink (Windows),
  remind the user to re-run `render.py --adapters-only` after editing skills.

## 4. Smoke test: every guard must fire

Run these on a throwaway branch and report a pass/fail table:

| Guard | Test | Expected |
|---|---|---|
| no commits on main | `git switch main`, then an empty commit attempt | refused by pre-commit |
| no .env commits | `git add -f .env`, then commit | refused; then `git restore --staged .env` |
| push gates | `git push` of a branch with a failing test | pre-push fails |
| path rules (Claude) | edit any file in `supabase/migrations/` | db-migrations rule injected |
| memory recall (Claude) | `python3 .claude/hooks/memory_recall.py "migration rls"` | no crash |
| CI | open a draft PR (the phase 7 PR) | `python`, `mobile`, `migrations-rls`, `gitleaks`, `actionlint`, `zizmor` and `harness` run |

`dependencies` (`security.yml`) runs too, and is deliberately not a required check: an
advisory published overnight would otherwise block every unrelated PR. A fresh Expo app
usually inherits a few high advisories in the SDK's own build tooling, so its first run
is often red. Look at each one: fix it, or record it in `mobile/npm-audit-allowlist.json`
with a reason and an `until` date at most 90 days out (`scripts/check_npm_audit.py`
documents the shape). Never allowlist one you haven't read.

Clean up the throwaway branch. Set `progress.harness: done`.
