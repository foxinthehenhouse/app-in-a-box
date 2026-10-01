---
name: reflect
description: Consolidate what recent sessions learned into the project's long-term memory (.agents/memory). Use at the end of a substantial session, after a correction from the user, after a painful debugging session, when the session-start healthcheck says reflect is overdue or a pending-reflection seed is waiting, or when MEMORY.md exceeds its budget.
---

# Reflect

Memory lives in `.agents/memory/`: one markdown note per lesson, indexed one line per
note in `MEMORY.md`, git-tracked so every agent and every machine sees it.

## 1. Gather signal

```bash
python3 .claude/hooks/harness_paths.py        # prints pending_reflection + captures paths
python3 .claude/hooks/pattern-extractor.py --days 14 --output text
git log --since="14 days ago" --pretty=format:"%h %ad %s" --date=short
```

Read the **pending-reflection seed** if the first command's `pending_reflection` file
exists (the Stop hook writes it after a session that touched 3+ files or committed). If
`transcripts_scanned` is 0, say so: the extractor is disconnected (run `harness-check`),
so "no corrections" means nothing.

For each correction or challenge the extractor found, ask: one-off, or a behaviour to
change? Seen 2x: write a `feedback_` note. Seen 3x: also propose a rule line for
AGENTS.md (the `harness-optimize` skill owns that change).

## What deserves a note

Only things that are **non-obvious and still true in 30 days**:
- a correction the user gave ("don't X, because Y")
- a trap that cost time (an env quirk, a misleading error, a tool that lies)
- a decision and its reason, if it isn't already in `docs/decision-log.md`

Not: code patterns, file paths, anything `grep` would find, session narration.

## Note format

`.agents/memory/<type>_<slug>.md`, where type is `feedback`, `ops`, `project`,
`reference` or `user`:

```
---
title: Short title
description: One line: the rule and why
tags: [area, tool]
---
The lesson in a few sentences. **How to apply:** the concrete behaviour change.
Related: [[other_note_slug]]
```

Then add one line to `MEMORY.md`: `- [Title](file.md): one-line description`.

## Consolidate

- Merge duplicates; update a stale note rather than adding a contradicting one.
- Link each new note to at least one related note (`[[slug]]`) where one exists.
- Keep `MEMORY.md` ≤ 45 lines; demote the least-used notes out of the index (they
  stay findable by the recall hook) rather than deleting lessons.
- Commit on a `chore/memory-<date>` branch and open a PR.

## Finish

Delete the seed and stamp the cadence clock (the session-start healthcheck reads it):

```bash
python3 -c "import sys,os; sys.path.insert(0,'.claude/hooks'); from harness_paths import pending_reflection_file as p; f=p(); os.path.exists(f) and os.remove(f)"
python3 .claude/hooks/harness_paths.py stamp reflect
```

Print: `Memory consolidated. N added, N updated, N removed.`
