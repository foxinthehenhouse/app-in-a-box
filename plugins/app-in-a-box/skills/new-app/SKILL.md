---
name: new-app
description: Orchestrates App in a Box end to end. It takes someone from a raw app idea to a provisioned, instrumented Expo + FastAPI + Supabase repo with CI, PR review and a full Claude Code harness. Run it in an empty folder. It resumes from appbox.yaml progress if interrupted.
disable-model-invocation: true
argument-hint: "[optional one-line idea]"
---

# App in a Box: orchestrator

You are standing up a production-grade mobile app from a cold start for someone who
may not be an engineer. Your job is to make the path feel short and the result feel
professional. Follow the phases in order. Each phase has its own skill file. Read it
fully before acting on it; don't paraphrase from memory.

`KIT` means the plugin root: the folder holding `skills/`, `scripts/` and
`template/`, i.e. two levels above this file. Resolve it once and write it to
`appbox.yaml` → `kit_root`:
- Claude Code plugin: `${CLAUDE_PLUGIN_ROOT}`.
- Codex plugin: the directory two levels above this `SKILL.md` (Codex shows you the
  skill's path).
- Pasted-prompt route: `<their clone>/plugins/app-in-a-box`.

## Agent compatibility (Claude Code and Codex)

This kit runs identically in both. Where they differ:

| Need | Claude Code | Codex |
|---|---|---|
| Ask a multiple-choice question | `AskUserQuestion` (1–4 questions, 2–4 options, multiSelect ok) | `request_user_input` if available (1–3 questions, 2–3 options; Plan mode by default). Otherwise ask in chat as a numbered list and wait. |
| Invoke a skill | `/app-in-a-box:<skill>` | `$<skill>` |
| Parallel subagents | `Agent` tool | spawn agents if enabled; else run the passes sequentially |
| Show an HTML mockup | publish/preview if available, else give the file path | give the file path (`open <file>` on macOS) |
| Network for CLIs | normal | needs `sandbox_workspace_write.network_access=true` or a full-access sandbox (see `KIT/docs/PERMISSIONS.md`) |

Wherever a phase says **"ask (structured)"**, use the row above. Keep every structured
question to at most 3 options plus "you pick" so it fits both tools.

## Operating principles (apply to every phase)

1. **The user owns decisions, you own mechanics.** Ask about product, taste, money
   and anything irreversible. Never ask about anything you can find out yourself:
   versions, whether a CLI is installed, which command to run.
2. **One question at a time is too slow. Twenty at once is a form.** Batch 2–3
   related questions per ask (structured), always with a recommended option first,
   marked "(Recommended)".
3. **Show, don't describe.** Design choices are shown as rendered HTML mockups, never
   as adjectives.
4. **Never put a secret in a tracked file.** Secrets go to `.env` (gitignored),
   `gh secret set`, `eas env:create` and Railway variables. `appbox.yaml` holds
   *names* and *IDs*, never values.
5. **Idempotent or it didn't happen.** Before creating any cloud resource, check
   whether it already exists (list projects, `gh repo view` and so on) and reuse it.
   Record every created resource's ID in `appbox.yaml` → `resources:`.
6. **Verify, don't assume.** A phase is done when its exit check passes, not when
   the commands ran. Report real output.
7. **Checkpoint.** After each phase, set `appbox.yaml` → `progress.<phase>: done`.
   Phases 0–3 have no repo yet, so they only update the file. Phase 4 makes the one
   bootstrap commit on `main` and turns on the git hooks, which refuse any later commit
   on `main`. From then on, checkpoints go on the branch `chore/appbox-setup`
   (`git switch -c chore/appbox-setup` right after the bootstrap commit), one commit
   per phase (`chore(appbox): <phase> complete`). Phase 7 opens that branch as the
   first PR, which is also the PR that proves CI and review work. Never skip the git
   hooks. `APPBOX_BOOTSTRAP=1` is used exactly twice: the phase 4 bootstrap commit
   and the phase 5 first push of `main`.
8. **Show progress.** Right after each checkpoint, run
   `python3 "$KIT/scripts/progress.py" appbox.yaml` and show its checklist verbatim,
   followed by one line on what the next phase needs from the user (or "nothing:
   I'll carry on"). The user should never have to ask "where are we?".
9. **When something fails,** check `KIT/docs/TROUBLESHOOTING.md` for the symptom
   before improvising. Every entry there came from a real run.

## Resume logic

If `appbox.yaml` exists, read `progress:` and jump to the first phase not marked
`done`. A project whose interview is done but that has no `progress.validate` key
predates the idea check: don't send it back to 1a. Offer the check once (it's
`validate-idea` on its own), and carry on from the next unfinished phase either way. Show the progress checklist (principle 8) and say in one line where you're
resuming. If every phase is done, don't restart: go to "Keep going" below.

## Phases

| # | Phase | Skill file | Exit check |
|---|---|---|---|
| 0 | Preflight | `KIT/skills/doctor/SKILL.md` (mode: preflight) | Required tools present; permission mode explained |
| 1a | Idea check | `KIT/skills/validate-idea/SKILL.md` | `docs/product/VALIDATION.md` written; verdict shown; user chose continue / sharpen / park |
| 1b | Interview | `KIT/skills/interview/SKILL.md` | `appbox.yaml` + `docs/product/BRIEF.md` written and confirmed |
| 2 | Design | `KIT/skills/design-directions/SKILL.md` | User picked a direction; `design/tokens.json` written |
| 3 | Accounts | `KIT/skills/accounts/SKILL.md` | Every required CLI reports logged in |
| 4 | Scaffold | `KIT/skills/scaffold/SKILL.md` | App boots locally; backend tests green; first commit on `main` |
| 5 | Provision | `KIT/skills/provision/SKILL.md` | Every resource in `appbox.yaml.resources` exists; secrets wired; migrations applied; `/health` 200 |
| 6 | Harness | `KIT/skills/harness/SKILL.md` | Git hooks on; GitHub protection + AI review; Claude + Codex adapters trusted; every guard smoke-tested |
| 7 | Verify | `KIT/skills/doctor/SKILL.md` (mode: full) | All gates green; first PR open; first analytics event seen |
| 8 | First feature | `KIT/skills/first-feature/SKILL.md` | Backlog seeded; feature #1 PR open |

If the user passed an idea as an argument (`$ARGUMENTS`), use it as the seed for
phase 1a's first question rather than asking "what's your idea?" cold.

**Phase 1a is advisory.** Whatever the verdict, the user chooses. On "park", stop
after showing progress; a later `new-app` run resumes at 1a with the report already
there, so offer "re-check the market" or "carry on" rather than starting over.

## Opening message (say this, in your own words, briefly)

> I'll turn your idea into a real app with a production setup around it: login,
> database, analytics, crash reporting, CI and an AI dev team that follows a proper
> spec → PR process. It's about an hour end to end. First I'll spend ~5 minutes
> checking the market: who else solves this and whether people are asking for it.
> Then you'll answer ~12 questions, pick a design, and click "sign in with GitHub" on
> a few free services. I handle the rest.
> Before we start: which permission mode are you running in? (If you get a lot of
> prompts, see KIT/docs/PERMISSIONS.md.)

If you're running in Codex, check the network now (`curl -sI https://registry.npmjs.org
| head -1`). If it fails, stop and give the relaunch command from
TROUBLESHOOTING.md → "Codex: every CLI fails with a network error" before phase 0
wastes the user's time.

Then show the (empty) progress checklist and run phase 0.

## Closing message (after phase 8)

Give the user, in this order:
1. The app running on their phone: the Expo Go QR code or dev build instructions.
2. Links: GitHub repo, first PR, Supabase dashboard, PostHog project, Sentry
   project, backend URL + `/health`.
3. "What I need from you", a short list of anything that truly needs a human
   (Apple enrolment, merging the first PR, adding a teammate).
4. The final progress checklist (all 10 steps ticked).

## Keep going (after phase 8, and whenever setup is already complete)

Setup ending shouldn't mean the guidance ends. Hand off to the generated repo's
own loop:

1. Run the repo's `next` skill (`/next` in Claude Code, `$next` in Codex). It reads
   PRs, CI, the backlog, overdue rituals and analytics, and proposes one action with
   two alternates. Offer its pick as a structured question and, on "go", run it.
2. Offer, once, to put the rituals on a schedule with the `routines` skill (weekly
   north-star report, dependency triage, reflect, harness-optimize). It creates
   nothing without a yes for each one.
3. Tell them the three habits that keep the repo moving on its own:
   - **Start any session by asking "what's next?"** The session-start line already
     gives a one-line hint.
   - **Describe features in plain words.** `feature-discovery` turns them into a spec,
     `build-feature` builds it, `pr-review` gates it.
   - **Ship with `ship`** when a build is ready for testers or the stores.

Set `progress.first_feature: done` only after the handoff, so a resumed run lands here.
