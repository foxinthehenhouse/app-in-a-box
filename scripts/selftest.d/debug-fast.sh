# Debug fast: sourced by selftest.sh with $KIT, $APP, $T and the check/refuses helpers.
# Flags carry an owner and an expiry (scripts/check_flags.py, wired into CI) and `next`
# surfaces the expired ones; backend tracing stays a low, scrubbed sample; every
# postmortem links the guard it added; docs/slo.yaml keeps its three SLOs; and the
# incident skill proposes the rollback before it diagnoses. Each guard passes on the
# rendered app and FAILS, naming its rule, on a planted violation. (The app's jest
# tests for traceparent, lib/flags.ts and the kill-push toggle run under --mobile.)
echo "Debug fast"

DF_PY="$APP/.venv/bin/python"

# _df_copy: a fresh copy of the rendered app to plant in, at $T/df (no .git).
_df_copy() {
  rm -rf "$T/df" && mkdir -p "$T/df" && (cd "$APP" && tar cf - --exclude=.git --exclude=node_modules .) | (cd "$T/df" && tar xf -)
}
# _df_flags <edit command>: check_flags.py must fail on the planted copy.
_df_flags() { _df_copy && (cd "$T/df" && eval "$1") && (cd "$T/df" && python3 scripts/check_flags.py); }
# _df_pytest <edit command> <test file>: that test must fail on the planted copy.
_df_pytest() { _df_copy && (cd "$T/df" && eval "$1") && (cd "$T/df" && "$DF_PY" -m pytest -q -p no:cacheprovider "$2"); }

# --- flags: owner + expiry, kill switches off by default, both sides agree ------------
check "flags: the rendered app's registries pass (mobile/lib/flags.ts + backend/flags.py)" \
  "cd '$APP' && out=\$(python3 scripts/check_flags.py) && grep -qF '2 flag(s), each with an owner and an expiry' <<<\"\$out\""
check "flags: CI runs scripts/check_flags.py" \
  "python3 -c \"import yaml; d=yaml.safe_load(open('$APP/.github/workflows/ci.yml')); assert any('scripts/check_flags.py' in str(s.get('run','')) for s in d['jobs']['python']['steps'])\""
refuses "flags: a mobile flag with no owner fails" \
  "_df_flags \"sed -i '/owner: \\\"@alex\\\",/d' mobile/lib/flags.ts\"" \
  "mobile/lib/flags.ts: kill-push: no owner"
refuses "flags: a backend flag with no expiry fails" \
  "_df_flags \"sed -i '/expires=\\\"2027-09-30\\\",/d' backend/flags.py\"" \
  "backend/flags.py: kill-push: no expiry"
refuses "flags: an expiry more than a year out fails" \
  "_df_flags \"sed -i 's/2027-09-30/2099-01-01/' mobile/lib/flags.ts\"" \
  "expires 2099-01-01 is more than a year out"
refuses "flags: a kill switch that defaults to on fails" \
  "_df_flags \"sed -i 's/default=False,/default=True,/' backend/flags.py\"" \
  "is a kill switch, so its default must be false"
refuses "flags: the app and the API disagreeing on one flag fails" \
  "_df_flags \"sed -i '/killSwitch: true,/d' mobile/lib/flags.ts && sed -i 's/kill-push/pause-push/' mobile/lib/flags.ts backend/flags.py && sed -i 's/kill_switch=True,//' backend/flags.py && sed -i 's/default: false,/default: true,/' mobile/lib/flags.ts\"" \
  "pause-push: default is True in mobile/lib/flags.ts but False in backend/flags.py"
refuses "flags: dropping the CI step unwires the guard (test_guards_wired)" \
  "_df_pytest \"sed -i '/check_flags.py/d' .github/workflows/ci.yml\" tests/harness/test_guards_wired.py" \
  "check_flags.py"
_df_stale() {
  _df_copy && sed -i 's/2027-09-30/2026-01-31/' "$T/df/mobile/lib/flags.ts" "$T/df/backend/flags.py" || return 1
  # Output captured first, never piped into `grep -q`: grep exits at the first match and
  # the writer dies of SIGPIPE, which pipefail reports as a failure.
  local out
  out=$(cd "$T/df" && python3 scripts/check_flags.py) || return 1
  grep -qF 'warning: mobile/lib/flags.ts: kill-push expired 2026-01-31' <<<"$out" || return 1
  out=$(cd "$T/df" && python3 scripts/check_flags.py --stale) || return 1
  grep -qF '"flag": "kill-push"' <<<"$out" || return 1
  out=$(CLAUDE_PROJECT_DIR="$T/df" python3 "$T/df/.agents/skills/next/signals.py") || return 1
  python3 -c "import json,sys; s=json.loads(sys.argv[1])['stale_flags']; assert [f['flag'] for f in s] == ['kill-push', 'kill-push'], s" "$out" || return 1
  out=$(CLAUDE_PROJECT_DIR="$T/df" python3 "$T/df/.agents/skills/next/signals.py" --line) || return 1
  grep -qF 'past their expiry, starting with `kill-push`' <<<"$out"
}
check "flags: an expired flag only warns in CI, and next surfaces it (JSON + session line)" _df_stale

# --- tracing: low sample, caller can't raise it, transactions scrubbed ----------------
check "tracing: the app's backend tests pass (sample rate, sampler, scrub, CORS)" \
  "cd '$APP' && '$DF_PY' -m pytest -q -p no:cacheprovider tests/test_observability.py"
refuses "tracing: a default sample rate of 100% fails" \
  "_df_pytest \"sed -i 's/^DEFAULT_TRACES_SAMPLE_RATE = 0.05/DEFAULT_TRACES_SAMPLE_RATE = 1.0/' backend/observability.py\" tests/test_observability.py" \
  "backend tracing must stay a low sample by default"
refuses "tracing: honouring the caller's sampled flag fails" \
  "_df_pytest \"sed -i 's/^        return rate$/        return 1.0 if sampling_context.get(\\\"parent_sampled\\\") else rate/' backend/observability.py\" tests/test_observability.py" \
  "test_sampler_ignores_the_callers_decision"
refuses "tracing: transactions sent unscrubbed fail" \
  "_df_pytest \"sed -i '/before_send_transaction=scrub_transaction,/d' backend/observability.py\" tests/test_observability.py" \
  "before_send_transaction"
check "tracing: the app sends traceparent next to X-Request-ID" \
  "grep -q '\"X-Request-ID\": requestId,' '$APP/mobile/lib/api.ts' && grep -q '\\.\\.\\.traceHeaders(requestId),' '$APP/mobile/lib/api.ts'"

# --- postmortems link their guard -------------------------------------------------------
# The postmortems are written to files first: their backticks would run inside eval.
printf '# Postmortem: x\n\n## Guard added\n\nWe will be more careful.\n' > "$T/pm-noguard.md"
printf '# Postmortem: x\n\n## Guard added\n\n`tests/test_gone.py`\n' > "$T/pm-gone.md"
printf '# Postmortem: x\n\n## Guard added\n\n`tests/test_slo.py::test_slo_file_is_complete`, planted.\n' > "$T/pm-good.md"
refuses "postmortems: one that names no guard fails" \
  "_df_pytest \"cp '$T/pm-noguard.md' docs/postmortems/2026-10-01-outage.md\" tests/test_postmortems.py" \
  "names no guard"
refuses "postmortems: one that links a guard that doesn't exist fails" \
  "_df_pytest \"cp '$T/pm-gone.md' docs/postmortems/2026-10-01-outage.md\" tests/test_postmortems.py" \
  "none is a guard file"
check "postmortems: one that links a real guard passes" \
  "_df_pytest \"cp '$T/pm-good.md' docs/postmortems/2026-10-01-outage.md\" tests/test_postmortems.py"

# --- SLOs ---------------------------------------------------------------------------------
check "slo: docs/slo.yaml passes and north-star-report reads it" \
  "cd '$APP' && '$DF_PY' -m pytest -q -p no:cacheprovider tests/test_slo.py"
refuses "slo: deleting the crash-free SLO fails" \
  "_df_pytest \"python3 -c \\\"import yaml; p='docs/slo.yaml'; d=yaml.safe_load(open(p)); d['slos']=[s for s in d['slos'] if s['id']!='crash_free']; yaml.safe_dump(d, open(p,'w'))\\\"\" tests/test_slo.py" \
  "crash_free: required SLO is missing"
refuses "slo: north-star-report dropping the SLO step fails" \
  "_df_pytest \"sed -i 's#docs/slo.yaml#the SLO file#g' .agents/skills/north-star-report/SKILL.md\" tests/test_slo.py" \
  "north-star-report no longer reads docs/slo.yaml"

# --- incident skill -------------------------------------------------------------------------
_df_incident_order() {
  python3 - "$APP/.agents/skills/incident/SKILL.md" <<'PY'
import sys
s = open(sys.argv[1]).read()
roll, diag = s.find("Propose the rollback first"), s.find("Find the line of code")
assert 0 < roll < diag, "the rollback proposal must come before diagnosis"
assert "docs/runbooks/incident.md" in s and "scripts/rollback-ota.sh" in s
assert "docs/postmortems/TEMPLATE.md" in s and "## Ask the owner" in s
PY
}
check "incident: the skill walks the runbook, proposes rollback before diagnosis, ends in a postmortem" _df_incident_order
check "incident: listed in owner_asks (rollbacks and user comms are the owner's call)" \
  "python3 -c \"import json; assert 'incident' in json.load(open('$APP/.claude/harness/manifest.json'))['owner_asks']['skills']\""
