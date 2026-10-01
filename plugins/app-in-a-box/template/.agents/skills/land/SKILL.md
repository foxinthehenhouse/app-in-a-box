---
name: land
description: Drive a pull request all the way to merged. Loops review → fix → resolve threads → push → wait for CI → re-review → merge, one step at a time, until the PR is merged or genuinely blocked; root-causes CI failures instead of re-running them, answers every review thread, and merges only when CI is green, the current commit is reviewed ✅, and the owner said merging is OK. Use after opening a PR, when asked to land/finish/babysit/get a PR merged, or when CI or a reviewer comments on a PR.
argument-hint: "[PR number] [--merge-ok]"
---

# Land a PR

`pr-review` judges one commit. `land` gets the PR from "opened" to "merged" across
pushes, CI runs and review comments, without the owner reading a diff.

## The loop

Ask the script what's next, do exactly that one thing, repeat:

```
python3 .agents/skills/land/land.py <PR> [--merge-ok]
```

Pass `--merge-ok` only when the owner has said, in this conversation or in
`AGENTS.md`, that green ✅ PRs may be merged without asking. It prints JSON with an
`action`. Do it, then run the script again. Stop on `done`, `ask_owner` or `blocked`.

| action | do this |
|---|---|
| `resolve_conflict` | `git fetch origin <base> && git merge origin/<base>` on the PR branch. Resolve by intent, regenerate lockfiles with their tool (never by hand), run the gates, commit, push. Ask the owner only when both sides changed the same behaviour and either choice loses something. |
| `fix_ci` | Open each failed check's log (`gh run view <id> --log-failed`). Find the **root cause**. Reproduce it locally, fix it, show the same check passing locally, commit, push. A failure in code this PR didn't touch: say so in one PR comment naming the check and why, then continue. "Flaky" is not a root cause. |
| `address_threads` | For each thread: if it's right, fix it and reply with the commit; if it's wrong, reply with why (evidence, one or two lines). Then resolve the thread. Reply to every thread, including bot findings. A design-level ask that's bigger than this PR goes to the owner as a question, not into the diff. |
| `wait_ci` | Wait for the checks on this head: `gh pr checks <PR> --watch --fail-fast` (give it up to 20 minutes). Then loop. |
| `review` | Run the `pr-review` skill on the current head. Its verdict comment carries the `appbox-verdict` marker, which is how this loop knows the head was reviewed. Every push needs a new review. |
| `fix_findings` | Fix the blockers from the latest verdict, push, loop (the push triggers a fresh review). |
| `mark_ready` | Only if the owner asked to land it: `gh pr ready <PR>`. Otherwise ask. |
| `merge` | `gh pr merge <PR> --squash --delete-branch --match-head-commit <head>`. Then confirm `done`. |
| `ask_owner` | Tell the owner where the PR stands in one short paragraph and what you need (see below). |
| `blocked` | Say exactly what's missing (gh login, no PR for this branch) and stop. |

**Waiting between events.** In Claude Code, prefer being woken: subscribe to the PR's
activity if your environment offers it, or schedule a check-in with a Routine
(`routines` skill) instead of sitting in a sleep loop. In Codex, `gh pr checks --watch`
is the wait. Never poll faster than CI can change.

## Never

- Skip, delete, weaken or quarantine a test to get green.
- Push an empty commit, or close and reopen the PR, to re-trigger CI.
- Rewrite history on a branch someone else works on: no rebase, amend or force-push.
  Merge the base in instead.
- Bypass a hook or a required check.
- Merge a draft, a red head, an unreviewed head, or with an open blocking thread.
- Leave a review thread unanswered.

Each push is proven first: run the gates the changed files touch, re-read your own
diff for what would make CI reject it, and push once. One validated push beats three
guesses.

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question
(recommended option first), never decide these silently. In this skill that means:
merging when they haven't said review-and-merge is OK; a ⚠️ verdict; a reviewer's
request that changes product behaviour, scope or the data model; and a conflict
where both sides changed the same behaviour. Report the PR's state in plain words
(what it does, what's green, what's waiting), then the one question.
