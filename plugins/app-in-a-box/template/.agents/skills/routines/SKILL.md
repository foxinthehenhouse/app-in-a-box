---
name: routines
description: Put the project's recurring rituals on a schedule, with the owner's consent. Weekly north-star report, dependency triage, Supabase advisor sweep, reflect and harness-optimize. Uses Claude Code Routines (cloud cron) where they fit, and documents the Codex / local cron equivalent. Use when asked to automate, schedule or "keep the project moving on its own", or after setup finishes.
disable-model-invocation: true
---

# Routines

Without a schedule, the rituals only run when the session-start line nags. This
skill sets them up to run on their own. **It creates nothing without an explicit yes
for each routine**, because every run spends tokens and can open PRs/issues.

## 1. Offer the menu (ask, structured, multi-select)

| Ritual | Cadence | What a run produces | Where it can run |
|---|---|---|---|
| `north-star-report` | Mon 08:xx | Report file + proposed tickets (issue comment; files nothing unapproved) | Cloud (needs the PostHog connector on the Routine) |
| Dependency triage | Mon 08:xx | `triage` pass over open dependency PRs + `npm audit` / `pip-audit`; one summary issue | Cloud |
| Supabase advisor sweep | Wed 08:xx | Security/performance advisors → one issue per new finding | Cloud (needs the Supabase connector) |
| `harness-optimize` | Fri 16:xx | Harness-change PR from the week's session signal | **Local**: it reads session transcripts on the machine where you work |
| `reflect` | Fri 16:xx | Memory notes PR | **Local**, same reason |

Estimated cost: each cloud run is one agent session, roughly a normal working
session's tokens. Say that in the question. Recommend the first two by default.

## 2. Create the ones they picked

**Claude Code (cloud Routines).** Run `/schedule` (alias `/routines`) and create one
routine per pick against this GitHub repo, with a prompt that stands alone because
each run starts fresh:

```
In <owner>/<repo>: run the <ritual> skill (.agents/skills/<ritual>/SKILL.md) end to end.
Never merge, never push to main, never file a ticket the skill says needs approval:
put proposals in one issue titled "<ritual>: week of <date>" instead.
```

Add only the connectors that ritual needs (PostHog, Supabase, Linear). Use a minute
that isn't :00 to avoid the top-of-hour rush. Manage or delete them later at
claude.ai/code/routines.

**Codex / any agent (local cron).** Codex has no cloud scheduler; use the machine's:

```cron
# crontab -e   (runs in the repo; logs to ~/.local/state/<slug>-rituals.log)
13 8 * * 1  codex exec -C /path/to/repo --approve-for-me -c sandbox_workspace_write.network_access=true "Use \$north-star-report." >> ~/.local/state/<slug>-rituals.log 2>&1
47 16 * * 5 codex exec -C /path/to/repo --approve-for-me -c sandbox_workspace_write.network_access=true "Use \$reflect, then \$harness-optimize." >> ~/.local/state/<slug>-rituals.log 2>&1
```

For Claude Code the local equivalent is
`cd /path/to/repo && claude -p "/harness-optimize" --permission-mode auto`. Cron
runs can't answer an approval prompt, so pick a mode that won't stop to ask. On macOS, prefer a
`launchd` agent (cron may lack disk access). Check the exact flags with
`codex exec --help` / `claude --help` first; CLIs drift.

## 3. Record it

Add each scheduled ritual's name to `.claude/harness/manifest.json` →
`cadence.scheduled` (e.g. `["north-star-report", "dependency-triage"]`), so the
session-start nudge stops asking you to run by hand what a routine already runs.
Commit that on a branch with a PR (`chore: schedule rituals`), and log it in
`docs/decision-log.md` (who agreed, what runs, where).

Reply with a table: ritual → where it runs → first run time → how to stop it.
