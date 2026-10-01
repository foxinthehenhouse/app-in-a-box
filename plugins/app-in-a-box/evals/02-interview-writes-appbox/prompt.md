---
max_turns: 20
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, Write]
runs: 3
---
Run the App in a Box interview skill. I can't answer interactively in this session,
so here are all my answers up front. Don't ask me anything; write `appbox.yaml` and
`docs/product/BRIEF.md` now (the kit root is wherever this plugin lives).

- Idea (a neutral test fixture, not an example app): "Sample List", a shared grocery
  list for people who live together.
- Core loop: someone adds an item → housemates see it → whoever shops ticks it off →
  everyone sees the list is done; you come back when the next item runs out.
- Platforms: iOS + Android. Accounts: email magic link + Apple + Google.
- Data: users type/photograph it. AI: no.
- Money: free while validating. Retention: notifications. Sensitive data: none.
- North star: households that tick off 5 items in their first 14 days.
- Tracker: GitHub Issues. Analytics: PostHog. Errors: Sentry. Hosting: Railway.
  Name: Sample List, handle `tester`.
- Just me for now.
