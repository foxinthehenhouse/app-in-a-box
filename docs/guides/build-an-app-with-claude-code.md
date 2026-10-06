# Build an iPhone and Android app with Claude Code

You have an idea and Claude Code. This page takes you from an empty folder to an app
running on your phone, with a real repo behind it. Nothing here needs you to know
React Native, FastAPI or Supabase; Claude does the engineering and asks you about the
product.

## What you need

- Claude Code on your computer. Phase 0 checks for git, Node, Python 3.12 and the
  service CLIs, and installs what's missing (you approve each install).
- An empty folder.
- About two hours, spread out however you like. You can stop after any phase.
- Free accounts you'll create along the way (GitHub, Supabase, Expo, PostHog, Sentry
  and a backend host). Apple's developer program ($99/yr) is only needed when you
  want TestFlight. To see the app on your phone before that, Expo Go is enough.

## 1. Install the plugin

In Claude Code, run these two commands once:

```
/plugin marketplace add foxinthehenhouse/app-in-a-box
```

```
/plugin install app-in-a-box@app-in-a-box
```

For fewer approval prompts on your own machine, start Claude Code with
`claude --permission-mode auto`. The other modes, and when bypass is safe (only in a
container), are in [PERMISSIONS.md](../../plugins/app-in-a-box/docs/PERMISSIONS.md).

## 2. Start in an empty folder

```
/app-in-a-box:new-app
```

You can add your idea on the same line (`/app-in-a-box:new-app a shared shopping list
for flatmates`) or just start talking. The
[`new-app`](../../plugins/app-in-a-box/skills/new-app/SKILL.md) skill runs every
phase in order and saves progress in `appbox.yaml`, so running it again picks up
where you left off.

## 3. What happens, and what you do

| Phase | Claude does | You do |
|---|---|---|
| Shape | Rae, the product advisor, plays your idea back as one page and asks only what's missing ([shape](../../plugins/app-in-a-box/skills/shape/SKILL.md)) | Talk, answer a few questions |
| Idea check | Researches competitors, complaints and pricing in the background, and gives a cited Go / Sharpen / Rethink verdict ([validate-idea](../../plugins/app-in-a-box/skills/validate-idea/SKILL.md)) | Read it, decide |
| Prototype | A design team builds a clickable prototype of every screen ([prototype](../../plugins/app-in-a-box/skills/prototype/SKILL.md)) | Click through, tune, approve |
| Accounts | Opens each signup page, then logs in the CLIs ([accounts](../../plugins/app-in-a-box/skills/accounts/SKILL.md)) | Click "Continue with GitHub" about six times |
| Scaffold | Creates the Expo app, overlays the template and shapes it to your brief ([scaffold](../../plugins/app-in-a-box/skills/scaffold/SKILL.md)) | Nothing |
| Provision | Creates the cloud projects and wires every secret, never into git ([provision](../../plugins/app-in-a-box/skills/provision/SKILL.md)) | Nothing |
| Harness | Turns on the git guards, branch protection and AI review, then proves each guard fires ([harness](../../plugins/app-in-a-box/skills/harness/SKILL.md)) | Nothing |
| Verify | Runs every gate, checks `/health` and the first analytics event | Open the app on your phone |
| First feature | Seeds a backlog and builds feature one as a PR ([first-feature](../../plugins/app-in-a-box/skills/first-feature/SKILL.md)) | Review the PR |

The full walkthrough, with rough times per phase, is in [START_HERE.md](../../START_HERE.md).

## What's specific to Claude Code

- Kit skills are namespaced: `/app-in-a-box:<skill>`. In the generated repo, its own
  skills are plain `/next`, `/backlog`, `/build-feature` and so on.
- The prototype team runs as parallel subagents.
- The generated repo's hooks inject the right rule when Claude edits a migration, an
  API contract or a screen, and recall memory at session start.
- Opt-in Claude Code Workflows give `build-feature` and `pr-review` a thorough mode
  that fans out reviewers. They cost several times the tokens, so they only run when
  you ask.

## After setup

Ask "what's next?" in the generated repo and the `next` skill proposes one action.
Features go through spec, tests, PR and review, and `land` drives each PR to merged.
[What's in the generated repo](what-you-get.md) explains every piece.

## Related

- [Quickstart](../../README.md#quickstart) · [The same with Codex](build-an-app-with-codex.md)
- [Turn an idea into a clickable prototype first](idea-to-clickable-prototype.md)
- [Ship to TestFlight and Google Play](ship-to-testflight-and-google-play.md)
- Something broke? [TROUBLESHOOTING.md](../../plugins/app-in-a-box/docs/TROUBLESHOOTING.md),
  or run the [`doctor`](../../plugins/app-in-a-box/skills/doctor/SKILL.md) skill.
