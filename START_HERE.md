# App in a Box: start here

You have an idea for a mobile app. This kit gets you from that idea to a real,
instrumented app on your phone, with a production-grade repo around it. It's the
setup a real production app was built with:

- an Expo (iOS/Android) app with auth, a design system, analytics and error monitoring
- a FastAPI backend on Supabase Postgres, with row-level security and a `/health`
  endpoint that tells you which features are wired
- a GitHub repo with CI, lint/type/test gates, AI PR review and branch protection
- an agent harness that works in **both Claude Code and Codex**: skills, subagents,
  hooks, path rules, memory and a spec → PR workflow, so your coding agent builds
  features the way a disciplined team would

You don't need to know how any of that works. You answer questions about your idea,
click "Continue with GitHub" on a few free services, and your agent does the rest.

---

## Quickstart for Codex (copy, paste, done)

In an empty folder, run these three lines. The `-c` flag gives Codex's sandbox
network access, which every setup CLI needs; without it phase 0 fails with DNS errors.

```
codex plugin marketplace add foxinthehenhouse/app-in-a-box
codex plugin add app-in-a-box@app-in-a-box
codex -c sandbox_workspace_write.network_access=true "Use \$new-app to build my app idea here."
```

Claude Code users: skip to Option A. Something broke? See
[`TROUBLESHOOTING.md`](plugins/app-in-a-box/docs/TROUBLESHOOTING.md).

## Option A: install the plugin (recommended)

This repo is a plugin marketplace for both agents.

**Claude Code**

```
/plugin marketplace add foxinthehenhouse/app-in-a-box
```

```
/plugin install app-in-a-box@app-in-a-box
```

Then, in an empty folder, run `/app-in-a-box:new-app`.

**Codex**

```
codex plugin marketplace add foxinthehenhouse/app-in-a-box
```

```
codex plugin add app-in-a-box@app-in-a-box
```

Then start Codex in an empty folder with network enabled and ask for `$new-app`:

```
codex -c sandbox_workspace_write.network_access=true "Use \$new-app to build my app idea here."
```

## Option B: no plugin, just paste a prompt (any agent)

Clone the kit and open an empty folder in Claude Code, Codex or any agent that can
read files and run a shell. Then paste:

```
Read <clone>/plugins/app-in-a-box/skills/new-app/SKILL.md and follow it
exactly. KIT is <clone>/plugins/app-in-a-box. Build my app in the current folder.
```

Every step lives in a markdown skill file, so the plugin and the paste-a-prompt route
run the same instructions in either agent.

---

## What happens, in order

| Phase | What your agent does | What you do | Time |
|---|---|---|---|
| 0. Preflight | Checks your machine for git, Node, Python 3.12 and the service CLIs, and installs what's missing | Approve installs | 5 min |
| 1a. Shape | Rae, your product advisor, lets you talk about the idea however it comes out (or paste notes or a voice transcript), plays it back as one page, asks only what's missing (2–3 questions a round) and gently challenges what might not work. It turns technical choices into plain consequences, so you never pick infrastructure. A risk screen flags ideas that touch children, location, health, money or other sensitive areas, asks only the questions that change how it's built, and turns on guardrails. Writes `docs/product/BRIEF.md`, `docs/product/RISK.md` and `appbox.yaml` | Talk; answer a few questions | 15–20 min |
| 1b. Idea check | Runs in the background while you talk: competitors, workarounds, real complaints from reviews and forums, what people already pay. A cited Go / Sharpen / Rethink verdict (`docs/product/VALIDATION.md`). Advisory: you always decide | Read the verdict; carry on, sharpen or park | 0 (runs alongside) |
| 2. Prototype | A team of design agents (flows, visuals, interaction, copy, and a critic who checks their work first) builds a clickable HTML prototype of every v1 screen. You switch the look (3 directions, light/dark), each screen's layout, minimal↔rich, calm↔playful motion and wording, and optional features, then freeze it. Optional Mobbin inspiration if you're connected | Click through, tune, approve | 30–45 min |
| 3. Accounts | Opens each free service's signup page, then logs the CLIs in | Click "Continue with GitHub" about 6 times | 10 min |
| 4. Scaffold | Generates the app, backend, migrations, design tokens and harness from your answers | Nothing | 10 min |
| 5. Provision | Creates the GitHub repo, Supabase, Expo, backend host, PostHog and Sentry projects, and wires every secret to the right place | Nothing | 10 min |
| 6. Harness | Turns on the git guards, branch protection and AI review, trusts the Claude/Codex adapters, and smoke-tests every guard | Trust the project in Codex, if you use it | 5 min |
| 7. Verify | Runs every gate, hits `/health`, opens the first PR, and confirms the first analytics event and error land (for the services you chose) | Open the app on your phone | 10 min |
| 8. First feature | Turns your brief into a backlog, then builds feature #1 through the spec → PR loop | Review the PR | ongoing |

You can stop at any phase. Progress is saved in `appbox.yaml` (`progress:`), and
re-running `new-app` resumes where you left off. After every phase your agent shows a
checklist like this one, so you always know where you are:

```
  [x] 0. Preflight: tools installed
  [x] 1a. Shape: your idea in your words: brief + appbox.yaml
  [x] 1b. Idea check: market researched, verdict + VALIDATION.md
  [>] 2. Prototype: clicked through, tuned and frozen: tokens + screens
  [ ] 3. Accounts: CLIs logged in
  ...
```

(Run it yourself any time: `python3 <kit>/plugins/app-in-a-box/scripts/progress.py appbox.yaml`.)

## After setup: the repo keeps itself moving

Setup ends, the guidance doesn't. The generated repo ships with:

- **`next`**: ask "what's next?" and it reads your PRs, CI, backlog, overdue
  rituals and analytics, then proposes one action and two alternates. Every session
  starts with a one-line version of it.
- **`north-star-report`**: a weekly readout of your 5 key events from PostHog, with
  the biggest drop-off turned into proposed tickets.
- **`market-watch`**: a monthly re-check of the market against your idea check:
  new competitors, price changes, new complaint themes. It proposes a ticket only
  when something actually changed.
- **`ship`**: the release checklist (version, EAS build/submit, OTA, store listing,
  privacy label, account deletion).
- **`routines`**: puts the weekly rituals on a schedule (Claude Code Routines, or cron
  for Codex), only with your yes for each one.
- **Evals** in `.agents/evals/` that measure whether the skills actually trigger and
  help (`claude plugin eval .agents`).
- **Model routing**: each AI teammate runs on the model that fits its job, with Fable
  for the final call on anything hard to undo. See
  [`MODEL_ROUTING.md`](plugins/app-in-a-box/docs/MODEL_ROUTING.md).
- **Workflows** (Claude Code, opt-in): thorough `build-feature` and `pr-review` runs
  that fan out reviewers and verify every finding. They cost several times the tokens
  of the normal skills, so they only run when you ask for them.

---

## Accounts you'll need

Each has a free tier big enough for a prototype. Sign up with GitHub wherever you
can, so each signup is one click.

| Service | Why | Free tier | Can the agent set it up? |
|---|---|---|---|
| GitHub | Code, CI, PR review | Yes | Repo, secrets and branch rules: yes. The account itself: you. |
| Supabase | Postgres, auth, storage | 2 projects; pauses after 7 idle days (the kit ships a keep-alive workflow) | Project, migrations and keys: yes, via CLI/MCP |
| Expo (EAS) | Builds, OTA updates, env vars | Limited monthly builds | Project and env vars: yes, via `eas` |
| Railway | Hosts the backend | Trial credit, then about $5/mo | Project, service, variables and domain: yes, via CLI/MCP |
| PostHog | Product analytics, flags, session replay | 1M events/mo | Project: yes, via API/MCP with a personal key |
| Sentry | Crash and error monitoring | Developer plan | Projects and DSNs: yes, via MCP/API |
| Better Stack | Uptime alerts on `/health` (or Sentry Uptime, if you use Sentry) | 10 monitors, 3-minute checks | Monitor: yes, via API with a token you paste |
| Cloudflare R2 | Nightly encrypted database backups (any S3-compatible store works) | 10 GB | Bucket and token: you. Wiring and the nightly job: yes |
| Anthropic / OpenAI | Only if your app has an AI feature | Pay as you go | No. You create the key. |
| Linear | Backlog (recommended; GitHub Issues is the alternative) | Free plan | Team: no. Projects and issues: yes. |
| Apple Developer | TestFlight / App Store (iOS only) | **$99/yr, not free** | No. Enrolment needs identity verification. |

**Why the agent can't click "sign up" for you:** every provider makes you accept its
terms, verify an email and often pass a CAPTCHA, and the kit deliberately won't create
accounts in your name. It handles everything *after* the account exists: it opens the
right page, waits for you, logs in the CLI and provisions the rest.

---

## Permissions: running without 50 approval prompts

Provisioning runs many shell commands. You pick a mode **when you launch**; neither
agent lets a plugin change it for you, and that's deliberate.

| | Safest | Recommended on your laptop | Fastest (container only) |
|---|---|---|---|
| Claude Code | `claude` | `claude --permission-mode auto` | bypass mode (see doc) |
| Codex | `codex -c sandbox_workspace_write.network_access=true` | `codex --approve-for-me -c sandbox_workspace_write.network_access=true` | `codex --yolo` |

The "fastest" column turns off every safety check. Only use it inside the kit's
`.devcontainer/` or a throwaway VM, where the agent can't touch your real files or
keys. Codex's sandbox blocks the network by default and the kit's CLIs need it, which
is why the `-c` flag is there. The exact flags for both agents, and the container
walkthrough, are in
[`plugins/app-in-a-box/docs/PERMISSIONS.md`](plugins/app-in-a-box/docs/PERMISSIONS.md).

---

## What this kit will not do

- Choose your product strategy. It asks and records; you decide.
- Create accounts in your name, or handle your Apple identity verification.
- Put a secret in a committed file. Secrets live in `.env` (gitignored), GitHub
  secrets, EAS env and Railway variables, and git hooks block anything that slips.
- Generate "AI slop" UI. You click through a prototype of every screen, checked
  against a taste rubric, before any code exists.
