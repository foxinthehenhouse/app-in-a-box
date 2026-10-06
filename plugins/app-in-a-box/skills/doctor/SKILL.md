---
name: doctor
description: App in a Box health check. In preflight mode it checks local tools and installs what's missing; in accounts mode it checks CLI logins; in full mode it checks tools, logins and repo gates, plus backend /health and the first analytics event. Use it before starting, after provisioning, or whenever something seems broken.
argument-hint: "[preflight|accounts|full]"
allowed-tools: "Bash(bash:*), Bash(gh:*), Bash(git:*), Bash(curl:*), Bash(python3:*), Read, Glob, Grep"
---

# Doctor

Run:

```
bash "$KIT/scripts/doctor.sh" <mode>
```

`$KIT` is the plugin root: `appbox.yaml` → `kit_root` if present, else
`${CLAUDE_PLUGIN_ROOT}` (Claude Code) or the folder two levels above this file (Codex /
pasted prompt).

## Preflight (phase 0)

1. Run `doctor.sh preflight`.
2. For each MISSING tool, install it yourself if the user's permission mode allows
   it. Prefer the package manager that's already present (`brew` on macOS,
   `npm i -g` for JS CLIs, `uv` for Python). Never pipe curl to a shell: download,
   show the first lines, then run.
3. Re-run until green. `railway` is only required if `stack.hosting: railway`.
   `maestro` and Xcode are optional.
4. Explain the permission modes in three lines and point to `$KIT/docs/PERMISSIONS.md`.
   Don't try to change the mode yourself. Only the user can, at launch.

## Accounts (end of phase 3)

`doctor.sh accounts`. Every service the `appbox.yaml` stack uses must be OK.

## Full (phase 7)

`API_URL=<backend url> doctor.sh full` from the app root, plus these checks the
script can't do:

- **First analytics event** (skip, and report "declined", if `stack.analytics: none`;
  then confirm instead that nothing tries to send). Open the app (Expo Go or a dev build), sign in, and
  confirm a `screen_viewed` event reaches PostHog. Use the PostHog MCP, or the
  PostHog "Activity" page. Dev builds have analytics disabled by design
  (`disabled: __DEV__`), so verify on a preview build or temporarily set
  `EXPO_PUBLIC_ANALYTICS_IN_DEV=1`.
- **First error** (skip if `stack.errors: none`; `/health` then lists error
  monitoring under `features_unavailable`, which is correct, not a failure). Hit `GET /debug/sentry` on the backend (enabled only when
  `APP_ENV != production`) and confirm the issue lands in Sentry.
- **PR loop.** A PR exists, CI ran on it, and the Claude review workflow commented.
- **Branch protection** (deferred from phase 6, because GitHub only offers checks it
  has seen). Once the first PR's checks have reported, run the `gh api -X PUT ...
  /protection` command from `$KIT/skills/harness/SKILL.md` § 2, then verify:
  ```
  gh api "repos/<owner>/<slug>/branches/main/protection" --jq '.required_status_checks.contexts'
  ```
  All six ids (`python`, `mobile`, `migrations-rls`, `gitleaks`, `ticket`, `pr-title`) must be
  listed. A 403 on a private repo means the GitHub plan has no branch protection:
  record `resources.github.protection: unavailable (plan)` in `appbox.yaml`, say so,
  and count the row as done (the git hooks still refuse commits on `main`). Record
  `resources.github.protection: on` otherwise.

Report a table: check → result → fix. "Green" means every row passes. Don't
round up. When every row is green, set `appbox.yaml` → `progress.verify: done` and
commit it on `chore/appbox-setup`; without that key a resumed `new-app` runs this
phase again. For the fix column, look the symptom up in `$KIT/docs/TROUBLESHOOTING.md`
first (Codex network, `EXPO_OFFLINE`, `ERESOLVE`, TypeScript 6 types, ruff, MCP
restart). Every entry there came from a real run.

## After setup

Once every phase is done, "what's wrong?" is usually "what's next?". Point the user
at the repo's `next` skill, which reads CI, PRs, the backlog and overdue rituals, and
at the `harness-check` skill for harness drift.
