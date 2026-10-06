# Build an iPhone and Android app with Codex

App in a Box runs the same skills in Codex as in Claude Code, and the repo it hands
you works the same in both. This page covers the Codex route, including the two
things that trip people up: network access and hook trust.

## What you need

- The Codex CLI on your computer. Phase 0 checks for git, Node, Python 3.12 and the
  service CLIs, and installs what's missing (you approve each install).
- An empty folder.
- About two hours, spread out however you like. You can stop after any phase.
- Free accounts you'll create along the way (GitHub, Supabase, Expo, PostHog, Sentry
  and a backend host). Apple's developer program ($99/yr) is only needed for
  TestFlight; Expo Go is enough to see the app on your phone before that.

## 1. Install the plugin

```
codex plugin marketplace add foxinthehenhouse/app-in-a-box
```

```
codex plugin add app-in-a-box@app-in-a-box
```

## 2. Start with network access

In an empty folder:

```
codex -c sandbox_workspace_write.network_access=true "Use \$new-app to build my app idea here."
```

The `-c` flag matters. Codex's `workspace-write` sandbox blocks the network by
default, and every setup CLI (`npm`, `gh`, `supabase`, `eas`) needs it; without the
flag, phase 0 fails with DNS errors. Once the repo exists, its `.codex/config.toml`
sets this for the project, after you trust it.

For fewer approval prompts on your own machine, add `--approve-for-me`. Full bypass
(`--yolo`) belongs only in the bundled dev container or a throwaway VM. Details:
[PERMISSIONS.md](../../plugins/app-in-a-box/docs/PERMISSIONS.md).

## 3. What happens

The [`new-app`](../../plugins/app-in-a-box/skills/new-app/SKILL.md) skill runs the
phases in order and saves progress in `appbox.yaml`, so re-running it resumes:

1. **Shape** and **idea check**: Rae, the product advisor, turns your ramble into a
   brief while the market research runs alongside
   ([shape](../../plugins/app-in-a-box/skills/shape/SKILL.md),
   [validate-idea](../../plugins/app-in-a-box/skills/validate-idea/SKILL.md)).
2. **Prototype**: a clickable prototype of every screen that you tune and freeze
   ([prototype](../../plugins/app-in-a-box/skills/prototype/SKILL.md)).
3. **Accounts**: it opens each signup page; you click "Continue with GitHub".
4. **Scaffold**, **provision**, **harness**, **verify**: it builds the repo, creates
   the cloud projects, turns on the guards and checks everything is wired.
5. **First feature**: a seeded backlog and feature one as a PR.

[START_HERE.md](../../START_HERE.md) has the full table with times.

## What's specific to Codex

- Skills are called with `$name`: `$new-app` for the kit, and `$next`, `$backlog`,
  `$build-feature` and so on in the generated repo.
- Multiple-choice questions use `request_user_input` when it's available; otherwise
  Codex asks in chat as a numbered list.
- Where Claude Code runs the prototype team as parallel subagents, Codex spawns
  agents if they're enabled and otherwise runs the passes one after another. The
  result is the same; it can take a little longer.
- **Trust the project once.** On first launch in the generated repo, Codex asks you
  to trust it; until then the project `.codex/config.toml` is ignored. It also asks
  you to approve each hook in `.codex/hooks.json` once.
- AI review on PRs: enable Codex code review for the repo in Codex's settings. It
  follows the "Review guidelines" section of the repo's `AGENTS.md`.

## How one repo serves both agents

Everything agent-facing lives in `AGENTS.md` and `.agents/` (skills, subagents,
rules, memory). The renderer generates `.codex/agents/*.toml`, `.codex/config.toml`
and `.codex/hooks.json` from those sources, and the Claude Code adapters from the
same files, so the two never drift. Edit the source, never the adapter.

## Related

- [Quickstart](../../README.md#quickstart) · [The same with Claude Code](build-an-app-with-claude-code.md)
- [What's in the generated repo, and why](what-you-get.md)
- Something broke? [TROUBLESHOOTING.md](../../plugins/app-in-a-box/docs/TROUBLESHOOTING.md),
  or run [`$doctor`](../../plugins/app-in-a-box/skills/doctor/SKILL.md).
