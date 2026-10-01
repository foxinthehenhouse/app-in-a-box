---
name: harness-check
description: Run the full self-learning harness integrity report (protected hooks and skills exist and are wired, capture is flowing, transcripts are visible, memory index matches disk, no ritual overdue). Use when a session-start drift note appears, when something about hooks or memory feels off, or after editing .claude/settings.json, .claude/hooks/ or .claude/harness/.
---

# Harness check

The same checker runs quietly at every session start and prints only drift and
overdue rituals. This is the full, loud version, with slower cross-checks
(extractor agreement, 3 days of hook runtime errors, latest CI run per workflow).

```bash
python3 .claude/hooks/harness-healthcheck.py
```

Exit 0 = healthy, 1 = drift. Report the real output.

## Fixing drift

- **Missing protected file**: restore it from git (`git log --oneline -- <path>`),
  or rebuild it from its `removal_rule` in `.claude/harness/manifest.json`.
- **Hook not registered**: add it back to `.claude/settings.json` under the event
  named in the manifest, then regenerate the Codex adapter (`.codex/hooks.json`,
  see `.agents/README.md`). This is the silent-death failure the check exists for.
- **Capture not flowing / not converging**: confirm `capture-activity.sh` is under
  `PostToolUse` and resolves its path only via `harness_paths.captures_dir()`.
  `python3 .claude/hooks/harness_paths.py` prints every resolved path.
- **Extractor sees 0 transcripts while capture logs sessions**: the signal source
  is disconnected. Check `transcripts` in the manifest against where your agent
  actually writes transcripts.
- **Memory index mismatch**: run the `reflect` skill to reconcile.

Only cadence directives, no FAILs: nothing is broken; run the `reflect` or
`harness-optimize` skill as suggested. Re-run until `All N checks passed.`
