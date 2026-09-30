---
name: interview
description: The App in a Box product interview. It asks about 12 structured questions in 4 rounds about the problem, users, core loop, data, monetisation and constraints, then writes appbox.yaml and docs/product/BRIEF.md. Use it when starting a new app or when the brief needs re-doing.
---

# Phase 1: Interview

Goal: learn enough in about 10 minutes to generate a correct data model, a sensible
screen map, the right integrations, and a CLAUDE.md that tells future agents what
matters. You are a senior PM running a crisp kickoff, not a form.

## Rules

- Use ask (structured) for multiple-choice rounds (see new-app → Agent compatibility;
  2–3 questions per call, at most 3 options + "you pick"). Put your
  **recommended** option first, labelled "(Recommended)", and base the
  recommendation on what they've already said.
- Use plain chat for the two open-ended questions (the idea and the core loop), and
  reflect your understanding back in one sentence before moving on.
- Don't ask what you can infer. If they said "habit tracker for runners", don't ask
  whether it's consumer or B2B.
- Offer "I don't know, you pick" on every choice, and if they pick it, choose the
  simplest option that keeps doors open.
- **Say why you're asking.** Each question below has a *Why we ask* line. Show it
  with the question, in the structured question's description where the tool has
  one or as a short line under it in chat. People answer better, and skip less, when
  they can see what the answer changes.
- Tell them at the start: about 12 questions in 4 short rounds, roughly 10 minutes.

## Round 1: the idea (open, in chat)

1. **"In a sentence or two: what's the app, and who is it for?"**
   Then reflect back: *"So: [user] who [struggle] will use [app] to [outcome]. Right?"*
   *Why we ask:* it becomes the first line every future agent reads about your app.
2. **"Walk me through the one thing a user does most often, start to finish."**
   This is the **core loop**. Extract: trigger → action → feedback → reason to return.
   If they describe five features, ask which one they'd keep if they could only
   ship one.
   *Why we ask:* the core loop decides the data model, the home screen and the
   analytics events, so it's the most load-bearing answer in the interview.

## Round 2: shape (ask, structured)

3. **Platforms:** iOS + Android via Expo (Recommended) · iOS only · Android only ·
   Also a web app. *Why:* sets the build profiles and which store accounts you'll need.
4. **Accounts:** Email magic link + Apple + Google (Recommended for consumer) ·
   Email + password only · No accounts at first (anonymous, local-only) ·
   Organisation/team accounts (B2B). *Why:* decides the auth setup, and whether every
   table is scoped per user or per team.
5. **Where does the data come from?** Users type it in (Recommended default) ·
   Device sensors/health data · Third-party APIs (name them) · Mix. *Why:* sensors
   and APIs add permissions, keys and failure modes the scaffold has to wire up.
6. **Does the product need AI?** No. Keep it deterministic (Recommended unless the
   core loop is conversational or generative) · Yes, a chat/assistant feature ·
   Yes, generation/summarisation behind the scenes · Not sure yet. *Why:* an AI
   feature needs an API key, a cost ceiling and a rule fencing where it's allowed.
   *If yes, record where the LLM is allowed. The generated CLAUDE.md fences the LLM
   into those modules, the same way Forge fences Claude into nutrition only.*

## Round 3: business and motivation (ask, structured)

7. **How will it make money (eventually)?** Free while validating (Recommended) ·
   Subscription · One-off purchase · Ads · B2B licence. *Why:* payments change store
   rules and the backlog. "Free for now" keeps every door open.
8. **What makes someone come back tomorrow?** Streaks/progress (gamification) ·
   Notifications/reminders · Social/community · Content that changes daily ·
   Utility (they need it when X happens). *Why:* it picks the retention features
   the backlog starts with, and the event that shows whether they work.
9. **Anything sensitive?** None · Health data · Financial data · Children under 13 ·
   Location. *Why:* each one adds a rule file the agents must follow, and store
   privacy answers you'll need at launch.
10. **What does success look like in 30 days?** Pick one north-star metric (offer
    3 suggestions derived from the core loop, e.g. "users who complete the core
    action 3× in week 1"). *Why:* the 5 analytics events, the weekly north-star
    report and the `next` skill all steer by this one number.

## Round 4: build constraints (ask, structured)

Claude Code plugin users can set defaults (`/plugin` → App in a Box → configure):
tracker `${user_config.default_tracker}`, hosting `${user_config.default_hosting}`.
If those read as real values rather than `${...}` placeholders, make them the
"(Recommended)" options below; otherwise (Codex, pasted prompt) use the defaults shown.

11. **Backlog tool:** GitHub Issues (Recommended: zero extra accounts) · Linear.
    *Why:* every change gets a ticket, and `next` reads this tracker to pick your work.
12. **Backend hosting:** Railway (Recommended: what Forge uses, about $5/mo after
    trial) · Fly.io · Render. *Why:* the only choice here with a monthly cost. (A
    Supabase-only stack with no Python backend isn't supported in v1.)
13. **Name + bundle ID:** Propose 3 name options if they don't have one. Derive
    `slug` (kebab-case) and `bundle_id` (`com.<their-handle>.<slug>`). Confirm.
    *Why:* the bundle ID is permanent once the app is in a store.
14. **Who else works on this?** Just me · Me + 1–2 friends · A team. *Why:* it changes
    the branch protection and review-bot defaults.

## Output 1: `appbox.yaml` (repo root, tracked, no secrets)

```yaml
version: 1
kit_root: <resolved KIT path>
app:
  name: "<Display Name>"
  slug: <kebab-slug>
  bundle_id: com.<owner>.<slug>
  one_liner: "<user> use <app> to <outcome>"
  platforms: [ios, android]
  owner_handle: <github-username>
product:
  target_user: "<who>"
  problem: "<struggle, in their words>"
  core_loop:
    trigger: "..."
    action: "..."
    feedback: "..."
    return_reason: "..."
  north_star: "<metric>"
  retention_mechanic: streaks|notifications|social|content|utility
  monetisation: free|subscription|one_off|ads|b2b
  sensitive_data: []          # health|financial|children|location
  ai:
    enabled: false
    allowed_modules: []       # e.g. backend/services/coach*
stack:
  mobile: expo
  backend: fastapi            # the only backend in v1
  hosting: railway            # railway|fly|render|none
  auth: [email_otp, apple, google]
  tracker: github             # github|linear
  analytics: posthog
  errors: sentry
design:
  direction: null             # filled in by phase 2
resources: {}                 # filled in by phase 5: IDs/URLs only, never secrets
progress:
  preflight: done
  interview: done
```

## Output 2: `docs/product/BRIEF.md`

Use this structure. Keep it to one page:

```markdown
# <App name>: product brief

**One-liner:** …
**Target user:** … **Problem (their words):** …

## Core loop
Trigger → Action → Feedback → Return reason (one line each)

## Screens (v1)
Derive 4–6 screens from the core loop, e.g. Onboarding · Home/Today · <Core action> ·
History/Progress · Settings. One line on each screen's job.

## Data model (v1)
Tables with key columns, derived from the core loop. Every table has `user_id`
and RLS.

## North-star metric + the 5 analytics events that measure it
## Out of scope for v1
## Open questions (things the user said "not sure" to)
```

## Exit check

Show the user the brief (not the yaml) and ask: "Does this capture it? Anything
wrong or missing?" Apply edits, then set `progress.interview: done`.
