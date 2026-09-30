---
max_turns: 20
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, Write]
runs: 3
---
Run the App in a Box interview skill. I can't answer interactively in this session,
so here are all my answers up front. Don't ask me anything; write `appbox.yaml` and
`docs/product/BRIEF.md` now (the kit root is wherever this plugin lives).

- Idea: "Lonely Socks": people with odd socks photograph a single sock and get matched
  with someone nearby who has its twin.
- Core loop: photograph a lonely sock → the app suggests likely matches → you confirm a
  match → you get a "reunited" streak; you come back when laundry day produces another orphan.
- Platforms: iOS + Android. Accounts: email magic link + Apple + Google.
- Data: users type/photograph it. AI: no.
- Money: free while validating. Retention: streaks. Sensitive data: location (approximate).
- North star: users who make 2 confirmed reunions in their first 14 days.
- Tracker: GitHub Issues. Hosting: Railway. Name: Lonely Socks, handle `alexk`.
- Just me for now.
