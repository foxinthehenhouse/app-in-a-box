---
max_turns: 25
timeout_seconds: 480
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
runs: 3
---
Run the App in a Box shape skill (phase 1a). I can't answer interactively in this session,
so here's my ramble and every answer up front. Don't ask me anything and skip the
background idea check; write the outputs now (the kit root is wherever this plugin lives).

Ramble: "Sample List" (a neutral test fixture, not an example app) is a shared grocery list
for people who live together. Someone notices we're out of oat milk, adds it, my housemates
see it straight away, whoever's at the shop ticks it off, and everyone sees the list is
done. Today we use a group chat and things get lost in it.

Answers: iOS + Android. Email magic link + Apple + Google sign-in. People type items or
snap a photo. No AI. Free while validating. Notifications bring people back. No sensitive
data. North star: households that tick off 5 items in their first 14 days. Maybe later:
recipes, price tracking. Tracker: GitHub Issues. Analytics: PostHog. Errors: Sentry.
Hosting: Railway. Name: Sample List, handle `tester`. Just me for now.
