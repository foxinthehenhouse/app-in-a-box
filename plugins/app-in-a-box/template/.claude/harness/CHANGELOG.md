# Harness changelog

Append-only record of changes to the self-learning harness. Each `harness-optimize`
run logs what it changed and the evidence behind it; each sunset logs its 3/3
capability re-test. Newest first.

## Conformance teardown: instructions became mechanisms (2026-10-02)

Each item replaced a sentence somebody had to remember with a check that fails, and each
check ships with a negative control in `tests/harness/`.

- **Memory recall pointed at a 404.** `memory_recall.py` rendered `.claude/memory/<note>`
  while the vault is `.agents/memory/`; every recall was a dead link. Fixed, and
  `test_memory_recall.py` runs the real hook against a seeded vault and requires every
  printed path to exist (a hook with the old prefix fails it).
- **The memory index is read for you.** `session-start.sh` prints the body of
  `.agents/memory/MEMORY.md` (bounded: 80 lines / 12 KB) instead of a count plus "read
  it". `harness-healthcheck.py` also lists notes in Claude Code's machine-local memory dir
  for this checkout that are not in `.agents/memory/` and nudges porting them via a PR
  (same slug derivation as transcripts; fails open when the dir is absent).
- **"A merged branch is dead" is now `.githooks/pre-push`.** For each pushed branch it asks
  `gh` for a merged PR; a merged PR whose head differs from the pushed sha refuses the push
  and names the PR. Fails open with a one-line notice when gh is missing, logged out or
  offline. Covered with a fake `gh` first on PATH.
- **Every hook command checks its file exists first.** A moved or deleted worktree used to
  kill every hook with exit 127, silently, and `bash-safety.sh` failed OPEN. Each
  `.claude/settings.json` command now falls back to `git rev-parse --show-toplevel` and,
  failing that, emits a `systemMessage` saying the hook is OFF and exits 0. The wrapper
  shape is pinned by `test_manifest.py` (and run against an empty project dir).
- **`warn-sensitive-files.py`** (PreToolUse on Write|Edit|MultiEdit) asks for confirmation
  before editing migrations, workflows, `eas.json`, `app.json`/`app.config.ts`, lock files
  and `.env*` (not `*.example`). Registered, protected, required. Registered hooks: 8/10.
- **Branch without a ticket id** gets a one-line SessionStart warning (`ABC-12` or `42-`).
- **Frontmatter whitelists.** Role lint rejects unknown keys and bad `model`/`effort`
  values; skill lint rejects unknown keys (both used to accept anything).
- **Path-rule table is checked glob by glob.** `test_rules_lint.py` now requires EVERY
  glob of a rule to appear in the AGENTS.md row that names it (it used to check only
  that the rule's name appeared somewhere). Rows fixed: `backend/models/**` dropped
  (no such dir), `mobile/app.json`, `backend/main.py` and
  `mobile/lib/analytics.ts` added.
- **Hook-event set widened** in `test_config_schemas.py` to the 2026-10 Claude Code list
  (`Setup`, `PostToolBatch`, `StopFailure`, `Task*`, `InstructionsLoaded`, `ConfigChange`,
  `CwdChanged`, `FileChanged`, `Worktree*`, `PostCompact`, `PreModelSwitch`), with
  matchers accepted on `Notification`, `Subagent*`, `PreCompact`, `InstructionsLoaded`
  and `ConfigChange`.
- **`.env.example` is deliberately readable.** The `Read` deny list names the real secret
  files (`.env`, `.env.local`, `.env.development`, `.env.production`, `mobile/.env`,
  `mobile/.env.local`) instead of `.env.*`, which also denied the example file that
  provisioning writes and agents need to read.
- Nits: duplicate `exit 0` in `bash-safety.sh` removed; devcontainer Node 20 -> 22;
  `test_manifest.py` checks each protected hook's declared event matches the
  settings.json event it is registered under.

## Installed: owner asks + living AGENTS.md

- `.agents/rules/product-judgement.md` + `manifest.json` → `owner_asks`, held by
  `tests/harness/test_owner_asks.py`: product-facing skills ask the owner, product
  roles return ⚖️ QUESTION blocks.
- AGENTS.md gained `## Product` and `## Where things live`, held current by
  `tests/harness/test_agents_md_current.py`. It stays within the 160-line budget:
  the Claude/Codex adapter table moved to `.agents/README.md` to make room.

## Installed: self-learning loop

- capture (`capture-activity.sh`) -> reflect seed (`session-reflect.sh`) ->
  extract (`pattern-extractor.py`, `skill-lifecycle.py`, `spend_ledger.py`) ->
  `reflect` + `harness-optimize` skills, with `harness-healthcheck.py` as the
  SessionStart drift sensor and cadence nudger. Protected list and budgets:
  `manifest.json`.
