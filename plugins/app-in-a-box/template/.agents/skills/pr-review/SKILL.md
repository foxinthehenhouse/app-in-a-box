---
name: pr-review
description: Review a pull request on the owner's behalf and fix what's safe to fix. Runs the deterministic gates first, then correctness/security, design-system, accessibility and analytics review passes, verifies each blocking finding, applies safe fixes, re-checks, and ends with a plain-English verdict. Use when a PR is opened, when asked to review a PR or branch, or before merging anything.
---

# PR review: the gate before main

Assume the owner doesn't read diffs. This review is the only thing standing between a
change and `main`, so be the careful engineer they don't have.

> **Thorough mode (Claude Code only, opt-in, ~5–10× the tokens):** if the owner asks
> for the workflow review, run the `pr-review` Workflow (`.claude/workflows/pr-review.js`)
> instead of steps 1–4. It fans out the same passes, has two skeptics verify each
> finding and loops the fixes, then hands you its result for step 5. This skill is
> the default route, and the only one in Codex.

## 0. Target

An explicit PR number, URL or branch; otherwise the PR for the current branch
(`gh pr view --json number,title,headRefName,baseRefName,isDraft,files,url`). No PR
means you stop and say so. Diff = `origin/<base>...HEAD`. Drafts get reviewed but
never merged.

## 1. Deterministic gates (cheap, fail fast)

Run only what the changed files touch:
- Backend or `*.py`: `scripts/dev-venv.sh python -m pytest -q`, then
  `scripts/dev-venv.sh ruff check backend tests`.
- Mobile: `cd mobile && npm run gates`.
- Migrations: read each new file against `.agents/rules/db-migrations.md`.
- A v1 response model changed: confirm `mobile/lib/api.ts` `*Wire` types match.

A red gate is finding #1. Fix it if the fix is mechanical; otherwise report it.

## 2. Review passes

Run these as parallel subagents if your agent supports them; otherwise sequentially.
Each pass returns findings as `severity (blocker|major|minor) · file:line · what
breaks · for whom`.

1. **Correctness + security:** logic bugs, unhandled errors, missing `user_id`
   scoping (IDOR), secrets in code, trusting ids from request bodies, in-process
   state, breaking wire changes (`.agents/rules/api-contract.md`).
2. **Design system + accessibility:** hex literals, raw sizes, non-ink text colours,
   missing `accessibilityRole`/label, tap targets < 48, meaning-by-colour-only.
3. **Analytics + env wiring:** new screen without a view event, mutation without
   success+failure events, new `EXPO_PUBLIC_*` or backend env var not wired
   (`.agents/rules/env-var-wiring.md`).
4. **Tests:** is the new behaviour tested? Would the test fail if the code were
   wrong? (Negative-control one important test mentally: delete the key line, and
   does anything go red?)

## 3. Verify before you believe

For every blocker/major: re-read the code path and try to disprove the finding.
Drop what doesn't survive. Reviewers hallucinate; the verdict must not.

## 4. Fix what's safe

Safe: mechanical lint/format, missing labels/testIDs, missing analytics call on a new
screen, an obvious missing `.eq("user_id", ...)` with a test proving it. **Not** safe:
anything changing product behaviour, schema or wire shape; ask instead. Never weaken
or delete a test to go green. Commit fixes to the PR branch
(`fix(review): <what>`), re-run the gates, and loop until green or 3 rounds.

## 4b. Chair ruling (risky PRs only)

Risky = touches auth/RLS, a migration, secrets/env/CI/build config, deletes files, or
is larger than ~400 net lines. For those, spawn the `chair` subagent once, with the
gate output, the verified findings and your classification (not the PR description:
it reads the diff first). In Codex, run the chair's instructions from
`.agents/agents/chair.md` as a final pass. An ESCALATE ruling means no merge. MERGE
on a risky PR still goes to the owner, because the chair can veto but can't authorise.

## 5. Verdict (plain English, top of your reply and as a PR comment)

```
Verdict: ✅ Safe to merge | ⚠️ Merge after owner decision | ❌ Not ready
What this PR does: <one sentence a non-engineer understands>
What I fixed: <bullets or "nothing">
What's left: <blockers with file:line, or "nothing">
Risk: low | medium | high, because <reason>
Chair: <MERGE/ESCALATE + its three reasons, or "not needed (low risk)">
```

Merge only if the owner has said review-and-merge is OK for low-risk PRs and the
verdict is ✅ with green CI. Squash merge, delete the branch.
