# Troubleshooting

Every entry here is a failure that happened during a real App in a Box run. Find
the symptom, apply the fix, then re-run the phase: `new-app` resumes from
`appbox.yaml` progress, so nothing already done is repeated.

Quick health check at any point: the `doctor` skill (`bash "$KIT/scripts/doctor.sh" full`).

## Setup and permissions

### Codex: every CLI fails with a network or DNS error
**Symptom:** `npm install`, `supabase`, `eas` or `gh` fail with `ENOTFOUND`,
`getaddrinfo` or "network is unreachable", but only in Codex.
**Why:** Codex's default sandbox blocks the network.
**Fix:** restart Codex with the network allowed for the workspace:
```
codex -c sandbox_workspace_write.network_access=true
```
Once the project is trusted, the generated `.codex/config.toml` sets this for you.
Details: [`PERMISSIONS.md`](PERMISSIONS.md).

### An MCP server I just connected has no tools
**Symptom:** you authorised Supabase / PostHog / Sentry / Linear with `/mcp` (or
`codex mcp login`), but the agent says the tools don't exist.
**Why:** both agents fix their tool list when the session starts.
**Fix:** restart the agent (quit, then reopen it in the same folder). Nothing is lost,
since progress lives in `appbox.yaml`. Every phase also has a CLI route, so the agent
can carry on without the MCP until you restart.

### Hundreds of approval prompts
**Fix:** relaunch in a less chatty mode (`claude --permission-mode auto`, or
`codex --approve-for-me -c sandbox_workspace_write.network_access=true`). No plugin
can change your mode for you; it's a launch flag. See `PERMISSIONS.md`.

## Mobile scaffold (phase 4)

### `npx expo install` fails with a proxy or fetch error
**Symptom:** `expo install` errors while contacting Expo's API (`FetchError`,
`ECONNRESET`, proxy 403), even though `npm install` works.
**Why:** `expo install` asks Expo's servers which versions match your SDK. Some
networks and sandboxes block that host.
**Fix:** prefix with `EXPO_OFFLINE=1`. Expo then uses the version map bundled with
the SDK, which is the same answer offline:
```
EXPO_OFFLINE=1 npx expo install <packages>
```

### npm `ERESOLVE` on react / react-dom
**Symptom:** `npm ERR! ERESOLVE unable to resolve dependency tree` mentioning
`react-dom` and a React version newer than the one Expo pinned.
**Why:** if `react-dom` isn't installed through `expo install`, npm picks the newest
one, which wants a newer React than your SDK ships.
**Fix:** install it the Expo way, in the same command as the other runtime deps:
`npx expo install react-dom ...`. If it's already wrong: `npm uninstall react-dom`,
then `npx expo install react-dom`. Don't reach for `--legacy-peer-deps`: it hides
the mismatch until runtime.

### `tsc` can't find `describe`, `it` or `expect` (TypeScript 6)
**Symptom:** `npm run gates` fails in `tsc --noEmit` with
`Cannot find name 'describe'` in test files.
**Why:** TypeScript 6 no longer includes every `@types/*` package automatically.
Only the ones listed in `compilerOptions.types` load.
**Fix:** the template's `mobile/tsconfig.json` already lists `"types": ["jest"]`.
If you replaced it, add that line back (and add `"node"` if you use Node globals in
scripts), and make sure `@types/jest` is installed.

## Provision (phase 5)

### The first push to `main` is refused by `bash-safety`
**Symptom:** in Claude Code, the one allowed push of `main` (`APPBOX_BOOTSTRAP=1 git
push -u origin main:main`, phase 5 step 1) is blocked with "pushing to main/master
directly", but only in a session that was resumed after the scaffold.
**Why:** that is the generated repo's own hook. Claude Code loads `.claude/settings.json`
at session start, so a run that began before phase 4 never had it; a resumed session
does, and the hook has no bootstrap flag (on purpose: it guards the agent, not you).
**Fix:** run that one command yourself, in a terminal, from the project folder. Then
tell the agent "done"; it verifies with `git ls-remote --heads origin main` and carries
on with the setup branch. Don't edit or disable the hook.

## Backend (phase 4 and CI)

### `ruff check` fails on a fresh checkout
**Symptom:** dozens of lint errors on untouched template code, often `B008` on
`Depends(...)`, or different results on your machine and in CI.
**Why:** ruff's default rule set changes between releases, so an unpinned config
lints differently depending on the version installed.
**Fix:** keep the pinned `[tool.ruff.lint] select = [...]` and the
`flake8-bugbear.extend-immutable-calls` list for FastAPI in `pyproject.toml`. If you
changed them, restore them from the template. Run it through the shared venv:
`scripts/dev-venv.sh ruff check backend tests`.

### `/health` says features are unavailable that you never asked for
**Fix:** each entry in `features_unavailable` names the env var it's missing. Set
that var (Railway variables for the deployed API, `.env` locally), or remove the
feature from `FEATURE_CONFIG` in `backend/config.py` if the app doesn't use it.

### Sign-in codes stop arriving, or Supabase says "email rate limit exceeded"
**Why:** the project is still on Supabase's built-in mailer, which allows a couple of
emails an hour and only exists for trying things out. Production `/health` lists
"email sign-in (custom SMTP)" under `features_unavailable` when this is the case.
**Fix:** provision step 2.7: a Resend API key (or any SMTP password) in `.env` as
`SMTP_PASS`, then `supabase_smtp.py`, then `AUTH_SMTP_HOST` on Railway. If codes still
don't arrive, the sender's domain isn't verified at the provider yet (Resend only
delivers to your own address until it is).

## After setup

### "The agent doesn't know what to do next"
Ask for `next` (`/next` in Claude Code, `$next` in Codex). It reads your PRs, CI,
backlog and analytics and proposes one action. The session-start line gives a
one-line version every time you open the project.

### A skill stopped triggering after I edited it
Run the skill evals: `claude plugin eval .agents --ablation with-without --no-publish`
(Claude Code). A case that dropped points at the edit that broke it.

Still stuck? Run the `doctor` skill in full mode and paste its table (it never prints
secret values) into an issue.
