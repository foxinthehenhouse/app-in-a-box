# Harness changelog

Append-only record of changes to the self-learning harness. Each `harness-optimize`
run logs what it changed and the evidence behind it; each sunset logs its 3/3
capability re-test. Newest first.

## Installed: self-learning loop

- capture (`capture-activity.sh`) -> reflect seed (`session-reflect.sh`) ->
  extract (`pattern-extractor.py`, `skill-lifecycle.py`, `spend_ledger.py`) ->
  `reflect` + `harness-optimize` skills, with `harness-healthcheck.py` as the
  SessionStart drift sensor and cadence nudger. Protected list and budgets:
  `manifest.json`.
