---
name: pr-review
description: Review a pull request on the owner's behalf and fix what's safe to fix. Runs the deterministic gates first, then correctness/security, design-system, accessibility and analytics review passes, verifies each blocking finding, applies safe fixes, re-checks, and ends with a plain-English verdict. Use when a PR is opened, when asked to review a PR, a branch or a pasted diff, or before merging anything.
allowed-tools: "Bash(gh:*), Bash(git:*), Bash(scripts/dev-venv.sh:*), Bash(npm:*), Bash(cd:*), Read, Glob, Grep, Edit, Write"
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
(`gh pr view --json number,title,headRefName,baseRefName,isDraft,files,url`). Diff =
`origin/<base>...HEAD`. Drafts get reviewed but never merged.

**Handed an inline diff** (pasted into the prompt, with no PR and no checkout)? Review
it as the PR: the same passes, the same verdict shape. The gates in step 1 can't run,
so name that in the verdict ("What's left: gates not run, no checkout") instead of
skipping it silently, and judge the tests by reading them: would each one go red if
the code were wrong? No PR and no diff means you stop and say so.

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
   missing `accessibilityRole`/label, tap targets < 48, meaning-by-colour-only, and
   the `docs/design/TASTE.md` rubric on any new or changed screen (one primary
   action, honest states, restraint, copy that is a verb and not a form label).
3. **Analytics + env wiring:** new screen without a view event, mutation without
   success+failure events, new `EXPO_PUBLIC_*` or backend env var not wired
   (`.agents/rules/env-var-wiring.md`).
4. **Context docs:** does `AGENTS.md` still describe the code after this PR? The map
   row for anything added, and any rule, product line or command the diff made
   untrue (the lint only checks the map and markers; the prose is yours to read).
5. **Tests:** is the new behaviour tested? Would the test fail if the code were
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
<!-- appbox-verdict sha=<full head sha you reviewed> result=safe|owner|not-ready -->
```

The last line is for the `land` skill: it is how the loop knows THIS commit was
reviewed (a later push needs a new verdict). `safe` = ✅, `owner` = ⚠️, `not-ready` = ❌.
Get the sha with `gh pr view --json headRefOid -q .headRefOid`.

Merge without asking only if `appbox.yaml` → `policy.auto_merge_low_risk` is `true`
(default `false`; only the owner flips it) or the owner said so in this conversation,
AND the verdict is ✅, the risk is low and CI is green. That is the same predicate
`land` takes as `--merge-ok`. Otherwise the owner merges. Squash merge, delete the
branch. To take a PR the rest of the way (CI, threads, re-review after each push,
merge), hand it to the `land` skill.

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: Findings that are product calls, not bugs: changed copy or flow, scope beyond the ticket, a new data field, a known limitation. Interactive: ask the owner before approving. In CI (review-only): post them as ⚖️ questions in the verdict comment and don't count them as blockers or approvals.
