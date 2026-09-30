---
name: harness-optimize
description: Self-tuning pass for the agent harness. Reads real session signal (corrections, tool and hook failures, skill usage, spend), turns recurring patterns into durable harness changes, runs a mandatory pruning pass, and opens a PR. Use weekly, when the session-start healthcheck says it is overdue, or when the complexity or spend budget is exceeded.
---

# Harness optimize

Closes the gap between the sensors (capture, extractor) and the guides (AGENTS.md,
skills, rules, memory): "the agent got corrected" becomes "the harness changed so it
won't need correcting again". Propose-first, evidence-cited, and it never touches a
protected component except as a verified improvement. Default window 7 days.

## 0. Hard gate: read the manifest

```bash
cat .claude/harness/manifest.json
```

For the rest of the run you MUST NOT remove, disable or move any `protected_*`
component for "budget", "looks unused" or "the model could do it ad hoc". The only
allowed change is a **verified net improvement**: build the strictly-better
replacement, confirm `harness-check` passes, update the manifest, retire the old one,
log it. A protected component that looks obsolete is **surfaced to the owner, never
removed**. A new component with zero usage is not a zombie; it is new.

## 1. Gather signal

```bash
python3 .claude/hooks/pattern-extractor.py --days 7 --output json
python3 .claude/hooks/harness-healthcheck.py || true
python3 .claude/hooks/skill-lifecycle.py || true
python3 .claude/hooks/spend_ledger.py --by agent || true
python3 .claude/hooks/harness_paths.py      # where captures / seed live
```

Skim the newest capture log (`<captures_dir>/*-activity.md`, last 40 lines).

- `transcripts_scanned: 0` means **disconnected, not a quiet week**. Every count,
  including `corrections: 0`, is meaningless. Stop, fix the wiring (`harness-check`),
  re-run. Same for exit 2 from `skill-lifecycle.py` / `spend_ledger.py`.
- Act on `tool_failures` (the agent flagged them). `tool_failures_suspected` are calls
  that **succeeded**; their text merely said "error". Never act on those alone.
- **Skill evals** (Claude Code): if `.agents/evals/results/` holds runs, compare the
  newest two `aggregate-result.json` files. A case whose score dropped, or a skill
  whose with-vs-without Δ is ≤ 0, is a skill that doesn't earn its context. Re-run
  after any skill edit you propose: `claude plugin eval .agents --ablation with-without --no-publish`.

## 2. Classify (first match wins)

| Signal | Change | Tier |
|---|---|---|
| Correction theme recurring 3+ times | a rule line in AGENTS.md / a `.agents/rules/` file | 🟡 propose |
| Correction seen 2x | a `feedback_` note in `.agents/memory/` (via `reflect` format) | 🟢 apply |
| Repeated `tool_failures` on one tool, or any `hook_failures` | config / permission / hook fix | 🟡 propose |
| Skill that exists but never fires when it should, or an eval case regressed | sharpen its `description` / body, prove it with the eval | 🟡 propose |
| Same manual orchestration across sessions | a new skill encoding it | 🟡 propose |
| Heaviest spend line out of proportion to its value | `model:` downgrade or prune | 🟡 propose |

🟢 = safe, reversible, file-local: apply now. 🟡 = changes behaviour or removes
something: propose and wait for the owner's go. When torn, pick 🟡.

## 3. Pruning pass (mandatory, even when the budget is clean)

A harness encodes what the model can't do *yet*, so a pass that only adds is broken.
Name at least one honest candidate, or say why there is none. Over budget (healthcheck
note) makes a prune mandatory. Candidates in order: `dormant` / `over-capacity` rows
from `skill-lifecycle.py` (never `probation`), a rule the agent now follows unprompted,
an AGENTS.md line restating default behaviour. For each:

1. **Capability re-test**: clean session *without* it, the task that motivated it, 3/3.
2. **Sunset, don't delete**: follow `manifest.sunset.protocol` (move to `.claude/_sunset/`,
   unregister hooks, regenerate `.codex/hooks.json`, log evidence, delete after two weeks).

Memory is **never** auto-pruned (that is `reflect`'s job, with the owner). All prunes are 🟡.

## 4. Propose, apply, verify

Print the proposal: 🟢 applying now / 🟡 proposed / pruning pass (candidate, re-test
result, decision; protected ones marked SURFACED) / complexity counts vs limits. Each line
cites its signal. Apply 🟢 and approved 🟡 items minimally, in the voice of the file, then:

```bash
python3 .claude/hooks/harness-healthcheck.py
```

## 5. Log, stamp, PR

Append `## <YYYY-MM-DD>: harness-optimize` with one line per change + evidence to
`.claude/harness/CHANGELOG.md`, then stamp the cadence clock:

```bash
python3 .claude/hooks/harness_paths.py stamp harness-optimize
```

Ship through the normal flow: a ticket (`backlog` skill), a `chore/<ticket>-harness-optimize`
branch in its own worktree (`new-worktree` skill), commit, push, open a PR citing the
evidence. Never commit on main. Summary line:
`Harness tuned: N applied, N proposed, N surfaced. PR: <url>. Next run in ~7d.`

## Rules

- Never remove or disable a protected component except as a verified improvement.
- Never propose off a disconnected sensor, or off a single correction (2x note, 3x rule).
- Precision over recall: a wrong harness change is worse than a missed one.
- The harness should **shrink** as the model improves.
