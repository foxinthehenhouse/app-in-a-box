---
name: north-star-report
description: Weekly product-analytics and reliability readout. Pulls the funnel of the brief's 5 north-star events from PostHog, finds the biggest drop-offs and errors, checks each SLO in docs/slo.yaml against its error budget, compares with last week, and proposes (then, with a yes, files) tickets that target them. Use weekly, when the session-start line says it's overdue, when the backlog is empty, or when asked "how is the app doing?".
---

# North-star report

The brief names one north-star metric and the 5 analytics events that measure it
(`docs/product/BRIEF.md` → "North-star metric + the 5 analytics events"). This turns
those events into next week's work.

## 1. Read the funnel

Needs the PostHog MCP (`/mcp` in Claude Code, `codex mcp login posthog` in Codex; a
newly authorised server only appears after the agent restarts). Without it, stop and
say so. Never guess numbers.

Query, for the last 7 days **and** the 7 before (so every number has a comparison):
1. A funnel over the 5 events in brief order, per unique user, 7-day conversion window.
2. Failures: mutation events with `success: false` (grouped by `error_code`) and
   `api_failed` (grouped by `path`, `status`). The shapes are in `mobile/lib/analytics.ts`.
3. Top 3 new or rising error-tracking issues (PostHog, or Sentry if connected).

Exclude internal users (the owner's own distinct ids, or a `$internal`/test cohort,
if one exists). Under ~30 users in the window: say "too few users to read drop-offs"
and report counts only. Percentages on tiny numbers mislead.

## 1b. Read the SLOs

`docs/slo.yaml` lists the reliability targets (availability, p95 latency, crash-free
sessions), each with its `source`. For each, read the value over the file's
`window_days` from that source: Sentry (MCP, or the web UI the owner reads out),
Railway HTTP metrics (Railway MCP), or PostHog `api_failed` as a rough stand-in for
availability. Work out the error budget left: for a percent SLO,
`1 - (100 - actual) / (100 - objective)`; for p95, whether it's under the objective.
Backend traces are sampled (`SENTRY_TRACES_SAMPLE_RATE`, 5% by default), which is
plenty for a p95 on real traffic but noisy under a few hundred requests a day: say so
rather than reading a spike into it. A source you can't reach is "not read", never
a guessed number.

## 2. Write it up

`docs/product/reports/<YYYY-WW>-north-star.md`:

```
# North star: <metric>, week <WW>
<metric value> (<+/-> vs last week)

| Step | Users | Conversion from previous | Last week |
|------|-------|--------------------------|-----------|

Biggest drop-off: <step A → step B>, <x%> lost. Likely because: <evidence: failure events, errors, a recent PR>
Failures: <event>: <n> (<+/->)
Errors: <issue>: <n users>

| SLO | Objective | Actual (<window_days>d) | Budget left |
|-----|-----------|-------------------------|-------------|
```

State the hypothesis as a guess with its evidence, not a finding. Mark it ⚖️ if
acting on it means a product tradeoff.

## 3. Propose tickets (at most 3)

For the biggest drop-off, any failure or error spike affecting > 5% of users, and any
SLO with under a quarter of its budget left (that one goes first: users can't convert
on an app that's down), draft a ticket: problem (with the numbers), hypothesis, acceptance criteria that name
the event the fix should move. Show them to the owner and ask (structured) which to
file. File the approved ones with the `backlog` skill (label `p1`, or `p0` if a
failure/error blocks the core loop).

## 4. Close

Stamp the ritual so the session-start nudge resets:

```bash
python3 .claude/hooks/harness_paths.py stamp north-star-report
```

Reply with the headline number, the drop-off, and the ticket links, in 5 lines.

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: Which proposed tickets to file, and any hypothesis that implies a product change (a flow, a feature, a metric). Ask before filing; never re-define the north star yourself.
