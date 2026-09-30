# Permissions: running the kit with fewer prompts

Provisioning runs a lot of shell commands: `supabase`, `eas`, `gh`, `railway`, `npm`.
Both agents let you choose how much to approve by hand. **Neither lets a plugin
change this for you.** You pick the mode when you launch, and that's a deliberate
safety property.

## Claude Code

| Mode | Launch with | What happens | Use when |
|---|---|---|---|
| Default | `claude` | Prompts for anything not allow-listed | You want to watch every step |
| Accept edits | `claude --permission-mode acceptEdits` | File edits auto-approved; shell still asks | Cautious first run |
| **Auto** | `claude --permission-mode auto` | A safety classifier approves or blocks each action instead of you | **Recommended on your own machine** |
| Bypass | `claude --dangerously-skip-permissions` | Nothing prompts | **Only in a container/VM** (see below) |

To make one the project default, set `permissions.defaultMode` in
`.claude/settings.local.json` (not committed). Organisations can forbid bypass with
`permissions.disableBypassPermissionsMode: "disable"`. Cloud sessions on claude.ai
ignore `bypassPermissions`/`dontAsk` from checked-in settings.

## Codex

| Mode | Launch with | What happens | Use when |
|---|---|---|---|
| Default | `codex` | `workspace-write` sandbox, asks when it needs more | You want to watch every step |
| **Auto-review** | `codex --approve-for-me` | An automatic reviewer handles approval requests inside the sandbox | **Recommended on your own machine** |
| Never ask | `codex -a never -s workspace-write` | Fails instead of asking | Scripted runs |
| Bypass | `codex --yolo` (= `--dangerously-bypass-approvals-and-sandbox`) | No sandbox, no approvals | **Only in a container/VM** |

**Codex needs network for provisioning.** The `workspace-write` sandbox blocks
network by default, so `npm`, `supabase`, `eas` and `gh` will fail. Either launch with

```
codex -c sandbox_workspace_write.network_access=true
```

or rely on the generated `.codex/config.toml`, which sets it for the project once
it's trusted. The kit runs from an empty folder, so use the flag for the first run.
(`--full-auto` no longer exists in current Codex; ignore docs that mention it.)

## The container route (bypass safely)

The generated repo ships `.devcontainer/devcontainer.json` (Node 20, Python 3.12, gh,
Claude Code, Codex, and the eas, supabase and railway CLIs). For the kit's own first
run:

1. Make an empty folder, copy `plugins/app-in-a-box/template/.devcontainer` into
   it, and open it in VS Code → **Reopen in Container**.
2. Inside the container, run `claude --dangerously-skip-permissions` or `codex --yolo`.
3. The agent can do anything *inside the container*. Your laptop's files, SSH keys
   and other credentials aren't mounted. The CLI logins you do inside it are the
   only credentials it holds.

Bypass still can't do three things, in either agent: sign up for accounts, pass
CAPTCHAs, or enrol you in Apple's developer program. Those stay with you.

The generated repo's hard guards (`.githooks/`: no commits on `main`, no staged
secrets, gates before push) still apply under bypass, because they're git hooks, not
agent permissions.
