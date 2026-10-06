# Supply chain of the GENERATED app: sourced by selftest.sh with $KIT, $APP (the
# rendered app, cwd), $T and the check/refuses helpers. Each guard is proven to pass on
# a pristine render and to FAIL, naming its rule, on a planted violation:
#   dependabot.yml          cooldown on every ecosystem (test_config_schemas.py)
#   scripts/check_lock.py   requirements*.txt and the hashed lock files agree (ci.yml)
#   --require-hashes        dev-venv + CI refuse a package whose hash doesn't match
#   test_supply_chain.py    hashed installs, `npm ci --ignore-scripts`, security.yml audits
#   check_npm_audit.py      high/critical npm advisories fail unless triaged (security.yml)
#   test_guards_wired.py    the new guard scripts are run by a workflow
# Every plant is made on a copy or reverted.
SC_PY="$APP/.venv/bin/python"
SC_PT="$SC_PY -m pytest -q -p no:cacheprovider -p no:warnings"
_sc_plant() { cp "$APP/$1" "$T/sc.bak"; }
_sc_unplant() { cp "$T/sc.bak" "$APP/$1"; }

check "supply chain: Dependabot waits out a cooldown on every ecosystem (7 days, 30 for a major)" \
  "python3 -c \"
import yaml
ups = {u['package-ecosystem']: u.get('cooldown') or {} for u in yaml.safe_load(open('$APP/.github/dependabot.yml'))['updates']}
assert set(ups) == {'pip', 'npm', 'github-actions'}, ups
assert all(c.get('default-days') == 7 for c in ups.values()), ups
assert ups['pip'].get('semver-major-days', 0) > 7 and ups['npm'].get('semver-major-days', 0) > 7, ups
\""
_sc_plant .github/dependabot.yml
python3 -c "
import yaml; p='$APP/.github/dependabot.yml'; d=yaml.safe_load(open(p))
d['updates'][1].pop('cooldown'); yaml.safe_dump(d, open(p, 'w'))"
refuses "supply chain: the dependabot test fails when npm's cooldown is removed" \
  "cd '$APP' && $SC_PT tests/harness/test_config_schemas.py -k 'test_dependabot and not can_fail'" \
  "npm: cooldown.default-days must be >= 7"
_sc_unplant .github/dependabot.yml

# The lock check, on the app and on planted drift in a copy.
_sc_lockcopy() {  # fresh copy of the app's requirement + lock files and the check
  rm -rf "$T/sc-lock" && mkdir -p "$T/sc-lock/scripts" \
    && cp "$APP"/requirements*.txt "$APP"/requirements*.lock "$T/sc-lock/" \
    && cp "$APP/scripts/check_lock.py" "$APP/scripts/dev-venv.sh" "$T/sc-lock/scripts/"
}
check "supply chain: the lock files match requirements*.txt on a pristine render" \
  "cd '$APP' && python3 scripts/check_lock.py"
_sc_lockcopy
sed -i.x 's/^httpx>=0.27,<0.29$/httpx>=0.28,<0.29/' "$T/sc-lock/requirements.txt" && rm -f "$T/sc-lock/requirements.txt.x"
refuses "supply chain: check_lock.py fails when requirements.txt changes without a re-lock" \
  "python3 '$T/sc-lock/scripts/check_lock.py' --root '$T/sc-lock'" \
  "requirements.lock is stale: requirements.txt changed since it was generated; run scripts/lock-deps.sh"
_sc_lockcopy
echo "left-pad>=1,<2" >> "$T/sc-lock/requirements-dev.txt"
refuses "supply chain: check_lock.py fails on a new dev package that isn't locked" \
  "python3 '$T/sc-lock/scripts/check_lock.py' --root '$T/sc-lock'" \
  "\`left-pad>=1,<2\` is not in the lock"
_sc_lockcopy
printf '# just a comment\n' >> "$T/sc-lock/requirements.txt"
check "supply chain: a comment-only edit needs no re-lock" \
  "python3 '$T/sc-lock/scripts/check_lock.py' --root '$T/sc-lock'"

# --require-hashes is real: a lock whose hashes for one package are wrong must not
# build a venv. (idna is tiny and in every lock; uv or pip, whichever is there.)
_sc_lockcopy
python3 - "$T/sc-lock/requirements-dev.lock" <<'PYEOF'
import re, sys
p = sys.argv[1]; s = open(p).read()
head = re.search(r"(?m)^idna==\S+ \\\n((?:    --hash=sha256:[0-9a-f]{64}(?: \\)?\n)+)", s)
assert head, "idna not in the lock"
s = s.replace(head.group(1), re.sub(r"[0-9a-f]{64}", "0" * 64, head.group(1)))
open(p, "w").write(s)
PYEOF
_sc_hash_refused() {
  local out
  out="$(APP_VENV_HOME="$T/sc-venvs" "$T/sc-lock/scripts/dev-venv.sh" 2>&1)" && return 1
  grep -Eiq 'hash mismatch|do not match the hashes' <<<"$out" || { printf '%s\n' "$out" | tail -5; return 1; }
}
check "supply chain: dev-venv refuses a package whose hash doesn't match the lock, and says so" "_sc_hash_refused"

# The app's own supply-chain test: green, then each rule on a plant.
check "supply chain: test_supply_chain.py + test_guards_wired.py green on a pristine render" \
  "cd '$APP' && $SC_PT tests/harness/test_supply_chain.py tests/harness/test_guards_wired.py"
_sc_plant .github/workflows/security.yml
python3 -c "
import re; p='$APP/.github/workflows/security.yml'; s=open(p).read()
s2=re.sub(r'(?ms)^      - name: pip-audit.*?(?=^      - )', '', s); assert s2 != s; open(p,'w').write(s2)"
refuses "supply chain: test_supply_chain.py fails when security.yml stops running pip-audit" \
  "cd '$APP' && $SC_PT tests/harness/test_supply_chain.py -k security_workflow" \
  "no pip-audit over a lock file"
_sc_unplant .github/workflows/security.yml
_sc_plant .github/workflows/ci.yml
sed -i.x 's/run: python -m pip install --require-hashes -r requirements-dev.lock/run: python -m pip install -r requirements.txt -r requirements-dev.txt/' \
  "$APP/.github/workflows/ci.yml" && rm -f "$APP/.github/workflows/ci.yml.x"
refuses "supply chain: test_supply_chain.py fails on an unhashed pip install in ci.yml" \
  "cd '$APP' && $SC_PT tests/harness/test_supply_chain.py -k 'hashed_and_scriptless and ci.yml'" \
  "must install a .lock with --require-hashes"
_sc_unplant .github/workflows/ci.yml
_sc_plant .github/workflows/ci.yml
sed -i.x 's/run: npm ci --ignore-scripts/run: npm ci/' "$APP/.github/workflows/ci.yml" && rm -f "$APP/.github/workflows/ci.yml.x"
refuses "supply chain: ...and on an \`npm ci\` that runs install scripts" \
  "cd '$APP' && $SC_PT tests/harness/test_supply_chain.py -k 'hashed_and_scriptless and ci.yml'" \
  "runs install scripts; add --ignore-scripts"
_sc_unplant .github/workflows/ci.yml
_sc_plant .github/workflows/ci.yml
python3 -c "
import re; p='$APP/.github/workflows/ci.yml'; s=open(p).read()
s2=re.sub(r'(?ms)^      - name: Lock files match.*?(?=^      - )', '', s); assert s2 != s; open(p,'w').write(s2)"
refuses "supply chain: test_guards_wired.py fails when no workflow runs check_lock.py" \
  "cd '$APP' && $SC_PT tests/harness/test_guards_wired.py -k every_guard_is_run" \
  "'check_lock.py'"
_sc_unplant .github/workflows/ci.yml

# check_npm_audit.py on a saved report: an untriaged high advisory fails, a triaged one
# passes, an expired triage fails again. (The real `npm audit` needs the registry.)
rm -rf "$T/sc-npm" && mkdir -p "$T/sc-npm/scripts" "$T/sc-npm/mobile" && cp "$APP/scripts/check_npm_audit.py" "$T/sc-npm/scripts/"
cat > "$T/sc-npm/report.json" <<'JSONEOF'
{"auditReportVersion": 2, "vulnerabilities": {
  "braces": {"name": "braces", "via": [{"name": "braces", "severity": "high",
    "title": "signature check", "url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc"}]},
  "@expo/cli": {"name": "@expo/cli", "via": ["braces"]}}}
JSONEOF
refuses "supply chain: check_npm_audit.py fails on an untriaged high advisory" \
  "python3 '$T/sc-npm/scripts/check_npm_audit.py' '$T/sc-npm/report.json'" \
  "high GHSA-aaaa-bbbb-cccc in braces"
_sc_allow() {  # <until>
  printf '{"GHSA-aaaa-bbbb-cccc": {"package": "braces", "reason": "build-time only, via @expo/cli", "until": "%s"}}\n' "$1" \
    > "$T/sc-npm/mobile/npm-audit-allowlist.json"
}
_sc_allow "$(python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=30))')"
check "supply chain: ...and passes once it is triaged with a reason and a date" \
  "python3 '$T/sc-npm/scripts/check_npm_audit.py' '$T/sc-npm/report.json'"
_sc_allow "2020-01-01"
refuses "supply chain: ...and fails again when the triage expires" \
  "python3 '$T/sc-npm/scripts/check_npm_audit.py' '$T/sc-npm/report.json'" \
  "expired on 2020-01-01; re-triage it"
echo '{"error": {"code": "ENOLOCK", "summary": "no lockfile"}}' > "$T/sc-npm/broken.json"
refuses "supply chain: check_npm_audit.py fails (not passes) when npm audit itself errored" \
  "python3 '$T/sc-npm/scripts/check_npm_audit.py' '$T/sc-npm/broken.json'" \
  "not an npm audit report"
