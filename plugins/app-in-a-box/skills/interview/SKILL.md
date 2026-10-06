---
name: interview
user-invocable: false
description: The App in a Box question bank and output spec: the questions about the payoff, who else is in it, platforms, accounts, data, AI, money, distribution, retention, sensitive data, services, hosting and name that the shape phase draws from for whatever is still unknown, when each one is asked (the decision ledger), and the exact appbox.yaml and docs/product/BRIEF.md formats. Use when someone wants to be walked through setup step by step, or when the brief needs re-doing.
---

# The interview (question bank)

Since v0.6, phase 1a is `skills/shape` (the founder rambles; the advisor asks only the
gaps). This skill is its **question bank and output spec**: `shape` draws the
questions below for whatever is still unknown, and writes Output 1 and Output 2
exactly as defined here. Run this skill on its own only when someone asks to be
walked through step by step.

Goal: learn enough in about 10 minutes to generate a correct data model, a sensible
screen map, the right integrations, and an AGENTS.md that tells future agents what
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
- Tell them at the start: about 17 questions in 4 short rounds, roughly 12 minutes.

## Round 1: the idea (open, in chat)

**Skip this round if shape (1a) or the idea check (1b) already asked it:** `appbox.yaml`
→ `product.problem` and `product.core_loop` are filled. Reflect the one-liner back in a
sentence and go straight to Round 2. Read `docs/product/VALIDATION.md` first if it
exists; its alternatives, complaints and riskiest assumptions sharpen every
recommendation below.

1. **"In a sentence or two: what's the app, and who is it for?"**
   Then reflect back: *"So: [user] who [struggle] will use [app] to [outcome]. Right?"*
   *Why we ask:* it becomes the first line every future agent reads about your app.
2. **"Walk me through the one thing a user does most often, start to finish."**
   This is the **core loop**. Extract: trigger → action → feedback → reason to return.
   If they describe five features, ask which one they'd keep if they could only
   ship one.
   *Why we ask:* the core loop decides the data model, the home screen and the
   analytics events, so it's the most load-bearing answer in the interview.

3. **"At the end of their first session, what should they feel?"** One feeling, in
   their words ("relieved it's handled", "proud of the streak"). This is the **payoff**.
   *Why we ask:* onboarding is built to reach it fast, and it's the one moment that gets
   an authored animation.

## Round 2: shape (ask, structured)

4. **Who else is in it?** Just them (Recommended unless they described other people) ·
   Shared with a few people they know · A community of strangers · Two sides (e.g.
   buyers and sellers). *Why:* it decides the data model, who can see what, invites, and
   whether the app is empty until other people join. It's the costliest answer to
   change later. *Community or two-sided:* also ask how the first user gets value before
   anyone else shows up (the cold start).
5. **Platforms:** iOS + Android via Expo (Recommended) · iOS only · Android only ·
   Also a web app. *Why:* sets the build profiles and which store accounts you'll need.
6. **Accounts:** Email magic link + Apple + Google (Recommended for consumer) ·
   Email + password only · No accounts at first (anonymous, local-only) ·
   Organisation/team accounts (B2B). *Why:* decides the auth setup, and whether every
   table is scoped per user or per team.
7. **Where does the data come from?** Users type it in (Recommended default) ·
   Device sensors/health data · Third-party APIs (name them) · Mix. *Why:* sensors
   and APIs add permissions, keys and failure modes the scaffold has to wire up.
8. **Does the product need AI?** No. Keep it deterministic (Recommended unless the
   core loop is conversational or generative) · Yes, a chat/assistant feature ·
   Yes, generation/summarisation behind the scenes · Not sure yet. *Why:* an AI
   feature needs an API key, a cost ceiling and a rule fencing where it's allowed.
   *If yes, record where the LLM is allowed. The generated AGENTS.md fences the LLM
   into those modules and nowhere else.*

## Round 3: business and motivation (ask, structured)

9. **How will it make money (eventually)?** Free while validating (Recommended) ·
   Subscription · One-off purchase · Ads · B2B licence. The model only: the price and
   where the paywall sits wait until just before launch. *Why:* payments change store
   rules and the backlog. "Free for now" keeps every door open.
10. **How will the first 100 users find it?** Friends and group chats (Recommended for
    shared apps: a share link) · An existing community they're in · App Store search ·
    Content or social posts · Sales (B2B). *Why:* it picks what v1 builds in for growth:
    a share sheet and deep links, invites, a web page, or store keywords.
11. **What makes someone come back tomorrow?** Streaks/progress (gamification) ·
    Notifications/reminders · Social/community · Content that changes daily ·
    Utility (they need it when X happens). *Why:* it picks the retention features
    the backlog starts with, and the event that shows whether they work.
12. **Anything sensitive?** None · Health data · Financial data · Children under 13 ·
    Location. *Why:* each one adds a rule file the agents must follow, and store
    privacy answers you'll need at launch. The risk screen (`skills/shape` → "The risk
    screen") asks only the follow-ups that change the architecture.
13. **What does success look like in 30 days?** Pick one north-star metric (offer
    3 suggestions derived from the core loop, e.g. "users who complete the core
    action 3× in week 1"). *Why:* the 5 analytics events, the weekly north-star
    report and the `next` skill all steer by this one number.
    *If VALIDATION.md exists:* recommend a metric, and choose the 5 events, so that
    at least one event measures the **top riskiest assumption** in its "How the app
    will measure it" column. The app's first week of data then answers the question
    the idea check couldn't.

## Round 4: build constraints (ask, structured)

Claude Code plugin users can set defaults (`/plugin` → App in a Box → configure):
tracker `${user_config.default_tracker}`, hosting `${user_config.default_hosting}`.
If those read as real values rather than `${...}` placeholders, make them the
"(Recommended)" options below; otherwise (Codex, pasted prompt) use the defaults shown.

14. **Services: which outside tools do you want?** Ask these together (structured),
    each with "you pick". Nothing here is required. Declining one skips its account,
    provisioning and MCP server, but the app keeps its typed calls as harmless no-ops,
    so turning it on later takes one key, not a rewrite.
    - **Ticket management:** Linear + its MCP (Recommended: agents file a ticket or
      sub-issue the moment they find new scope, a bug or a follow-up, so nothing gets
      lost in chat; free for small teams) · GitHub Issues (zero extra accounts).
      *Why:* every change gets a ticket, and `next` reads this tracker to pick your work.
    - **Product analytics:** PostHog (Recommended: free tier; the north-star report,
      `next` and `market-watch` read it) · Not now. *Why:* without it you can't see
      whether the riskiest assumption from the idea check holds.
    - **Error monitoring:** Sentry (Recommended: free tier; crashes arrive with the
      request id the user sees) · Not now. *Why:* without it you learn about crashes
      from store reviews.
15. **Backend hosting:** Railway (Recommended: what the kit is built and tested on, about $5/mo after
    trial) · Fly.io · Render. *Why:* the only choice here with a monthly cost. (A
    Supabase-only stack with no Python backend isn't supported in v1.)
16. **Name + bundle ID:** Propose 3 name options if they don't have one. Derive
    `slug` (kebab-case) and `bundle_id` (`com.<their-handle>.<slug>`). Confirm.
    *Why:* the bundle ID is permanent once the app is in a store.
17. **Who else works on this?** Just me · Me + 1–2 friends · A team. *Why:* it changes
    the branch protection and review-bot defaults.

## When each question is asked (the decision ledger)

Shape doesn't walk this list. It asks **only what's expensive to change on day 0** (at
most 7 questions), states most of the rest as defaults, and defers the remainder to the
phase where it matters, recording each in `design/brief.json` → `decisions` (schema in
`docs/COST.md` → "The brief"):

| Question | When | Status if not asked |
|---|---|---|
| 1 idea + who, 2 core loop + moment and frequency, 3 payoff | `shape` (day 0) | inferred from the ramble where possible |
| 4 who else is in it, 9 money model, 10 first 100 users, 12 sensitive data | `shape` (day 0) | stated as a default if the ramble makes it obvious |
| 5 platforms, 6 accounts, 7 data source, 8 AI, 11 come-back reason, 13 north star | `shape` | `default` ("I'm assuming…, say if not") |
| 14 services, 15 hosting, 17 who else works on it | `shape` default, confirmed at `scaffold` | `default` |
| 16 name + bundle ID | `scaffold` (a working title until then) | `deferred` |
| Look and feel, copy tone, which maybe-features make v1 | `prototype` | `deferred` |
| Integrations the v1 features imply (payments, push, social sign-in) | `scaffold` | `deferred` |
| Nudge policy, when to ask for each permission | `first-feature` | `deferred` |
| Price and paywall placement, store listing and keywords, privacy labels, support channel | `pre-launch` | `deferred` |

Walked step by step (this skill on its own), ask them all, but still record each answer
in the ledger as `asked`.

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
  context: "<how often, and where they are when they reach for it>"
  payoff: "<what they feel at the end of the first session>"
  social: solo|shared|community|two_sided
  distribution: "<how the first 100 users find it>"
  north_star: "<metric>"
  retention_mechanic: streaks|notifications|social|content|utility
  monetisation: free|subscription|one_off|ads|b2b   # the model; price waits for pre-launch
  sensitive_data: []          # health|financial|children|location
  ai:
    enabled: false
    allowed_modules: []       # e.g. backend/services/coach*
stack:
  mobile: expo
  backend: fastapi            # the only backend in v1
  hosting: railway            # railway|fly|render|none
  auth: [email_otp, apple, google]
  tracker: linear             # linear|github
  analytics: posthog          # posthog|none (none keeps no-op calls in the app)
  errors: sentry              # sentry|none (same)
design:
  direction: null             # filled in by phase 2
policy:
  auto_merge_low_risk: false  # true lets pr-review / land squash-merge a ✅ low-risk PR with green CI without asking; the owner flips it
resources: {}                 # filled in by phase 5: IDs/URLs only, never secrets
validation: {}               # written by phase 1b (verdict, depth, decision, report)
progress:
  preflight: done
  validate: done              # set by phase 1b (done|parked); leave as it is
  interview: done
```

`appbox.yaml` may already exist from shape (1a) or the idea check (1b). **Merge into
it**: keep `validation`, `product.*` and `progress.validate` exactly as they wrote them.

## Output 2: `docs/product/BRIEF.md`

Use this structure. Keep it to one page:

```markdown
# <App name>: product brief

**One-liner:** …
**Target user:** … **Problem (their words):** …

## Core loop
Trigger → Action → Feedback → Return reason (one line each)

## Payoff
What they must feel by the end of the first session, and the moment that delivers it
(the one authored animation).

## Social shape
Solo, shared with a few, community or two-sided, and (for the last two) how the first
user gets value before anyone else joins.

## Distribution
How the first 100 users find it, and what v1 builds in for that (share link, invites,
web page, store keywords).

## Screens (v1)
Derive 4–6 screens from the core loop, e.g. Onboarding · Home/Today · <Core action> ·
History/Progress · Settings. One line on each screen's job.

## Data model (v1)
Tables with key columns, derived from the core loop. Every table has `user_id`
and RLS.

## Positioning
(Only if VALIDATION.md exists.) One or two lines: for <target user> who <problem>,
unlike <the named alternatives>, this app <the angle>. Link VALIDATION.md.

## Riskiest assumptions
(Only if VALIDATION.md exists.) Copy its table, and name the analytics event that
measures each one.

## North-star metric + the 5 analytics events that measure it
## Out of scope for v1
## Decisions still to make
From `design/brief.json` → `decisions`, every `deferred` entry: the question and the
phase that will ask it (e.g. "Price and paywall placement: pre-launch").
## Open questions (things the user said "not sure" to)
```

## Exit check

Show the user the brief (not the yaml) and ask: "Does this capture it? Anything
wrong or missing?" Apply edits, then set `progress.interview: done`.
