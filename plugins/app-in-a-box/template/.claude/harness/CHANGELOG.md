# Harness changelog

Append-only record of changes to the self-learning harness. Each `harness-optimize`
run logs what it changed and the evidence behind it; each sunset logs its 3/3
capability re-test. Newest first.

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
