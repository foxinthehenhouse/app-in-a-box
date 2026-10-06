# Privacy data map: privacy/data-map.yaml declares every column, analytics prop and
# permission in the generated app, and the store answers, PrivacyInfo entries and policy
# draft are generated from it. Sourced by selftest.sh with $KIT, $APP, $T and the
# check/refuses/skip helpers.
#
# Proven here: the pristine render passes; each rule FAILS on a planted violation with its
# own message (on a copy, never $APP); the render sets `packs` from the brief's risk
# screen; CI and pre-commit run the check, and the wiring test notices when they stop.
DMP_FILES="privacy supabase/migrations mobile/lib/analytics.ts mobile/app.json scripts/check_data_map.py scripts/schema_sql.py"

check "data map: the pristine render's map is complete and its generated answers current" \
  "cd '$APP' && python3 scripts/check_data_map.py"
check "data map: the render ships the map, the three drafts and an iOS privacy manifest in app.json" \
  "cd '$APP' && [ -f privacy/data-map.yaml ] && [ -f privacy/APP_STORE.md ] && [ -f privacy/PLAY_DATA_SAFETY.md ] \
   && grep -q '^# Privacy policy for Penny Jar (DRAFT)$' privacy/PRIVACY_POLICY.md && grep -q 'not legal advice' privacy/PRIVACY_POLICY.md \
   && python3 -c \"import json; pm=json.load(open('mobile/app.json'))['expo']['ios']['privacyManifests']; assert pm['NSPrivacyTracking'] is False and pm['NSPrivacyCollectedDataTypes'] and {a['NSPrivacyAccessedAPIType'] for a in pm['NSPrivacyAccessedAPITypes']} >= {'NSPrivacyAccessedAPICategoryUserDefaults'}\""

_dmp_copy() {  # <dir>: the files the guard reads, copied from the rendered app
  rm -rf "$1" && mkdir -p "$1" && (cd "$APP" && tar -cf - $DMP_FILES) | (cd "$1" && tar -xf -)
}

# _dmp_refuses <python edit, run in the copy's root with `m` = the map (dict), `a` = app.json
# (dict), `p` = pathlib.Path> <expected message>: plant it, the guard must fail on that message.
_dmp_refuses() {
  local d="$T/dmp-neg"; _dmp_copy "$d" || return 1
  (cd "$d" && python3 - "$1" <<'PYEOF') || return 1
import json, pathlib as p, sys, yaml
m = yaml.safe_load(open("privacy/data-map.yaml")); a = json.load(open("mobile/app.json"))
exec(sys.argv[1])
yaml.safe_dump(m, open("privacy/data-map.yaml", "w"), sort_keys=False)
json.dump(a, open("mobile/app.json", "w"), indent=2)
PYEOF
  local out rc; out=$(cd "$d" && python3 scripts/check_data_map.py); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -qF -- "$2" && printf '%s\n' "$out" | grep -q '^data map check FAILED' \
    || { printf '%s\n' "$out"; return 1; }
}
check "data map catches: a migration column missing from the map" \
  "_dmp_refuses \"p.Path('supabase/migrations/20990101000000_x.sql').write_text('alter table public.profiles add column birthday date;')\" \
   'data map: column profiles.birthday (supabase/migrations) is not in privacy/data-map.yaml'"
check "data map catches: an analytics prop missing from the map" \
  "_dmp_refuses \"f = p.Path('mobile/lib/analytics.ts'); f.write_text(f.read_text().replace('capture(\\\"push_opened\\\", { route })', 'capture(\\\"push_opened\\\", { route, title })'))\" \
   \"data map: analytics prop 'push_opened.title' (mobile/lib/analytics.ts) is not in privacy/data-map.yaml\""
check "data map catches: an app.json permission missing from the map" \
  "_dmp_refuses \"a['expo']['plugins'].append(['expo-location', {'locationWhenInUsePermission': 'Show the parks near you on the map.'}])\" \
   \"data map: permission 'location_when_in_use' (mobile/app.json: plugin expo-location locationWhenInUsePermission) is not in privacy/data-map.yaml\""
check "data map catches: a sensitive category with no retention" \
  "_dmp_refuses \"del m['tables']['auth.users']['columns']['email']['retention']\" \
   \"privacy/data-map.yaml: auth.users.email is 'contact' (sensitive) but has no retention\""
check "data map catches: a sensitive category sent to analytics" \
  "_dmp_refuses \"m['analytics']['push_opened']['props']['route'] = 'health'\" \
   \"privacy/data-map.yaml: analytics prop 'push_opened.route' is 'health': sensitive data never goes to analytics\""
check "data map catches: a generic permission purpose" \
  "_dmp_refuses \"m['permissions']['notifications'] = 'Needed for app functionality.'\" \
   \"privacy/data-map.yaml: permission 'notifications' has a generic purpose ('Needed for app functionality.')\""
check "data map catches: a plugin's generic default permission text in app.json" \
  "_dmp_refuses \"a['expo']['plugins'].append('expo-camera'); m['permissions'].update(camera='scan the barcode on a jar to add it', microphone='record a voice note about a jar')\" \
   \"data map: permission 'camera' (mobile/app.json: plugin expo-camera cameraPermission) ships the plugin's generic default text\""
check "data map catches: retention: account on a table the account deletion doesn't reach" \
  "_dmp_refuses \"m['tables']['rate_limits']['columns']['key']['retention'] = 'account'\" \
   \"data map: rate_limits.key says retention: account, but rate_limits isn't deleted with the account\""
check "data map catches: a stale generated file (map edited, nobody regenerated)" \
  "_dmp_refuses \"m['tables']['profiles']['columns']['display_name']['purpose'] = 'greet you by name'\" \
   'privacy/PRIVACY_POLICY.md is stale (it no longer matches privacy/data-map.yaml): run python3 scripts/check_data_map.py --write'"
check "data map catches: a stale iOS privacy manifest in app.json" \
  "_dmp_refuses \"a['expo']['ios']['privacyManifests']['NSPrivacyCollectedDataTypes'] = []\" \
   'mobile/app.json expo.ios.privacyManifests is stale'"
check "data map catches: a hand edit to a generated store answer" \
  "_dmp_refuses \"f = p.Path('privacy/APP_STORE.md'); f.write_text(f.read_text().replace('| Email Address |', '| Email |'))\" \
   'privacy/APP_STORE.md is stale'"
_dmp_write_fixes() {  # --write regenerates exactly what --check wanted, and stays put
  local d="$T/dmp-write"; _dmp_copy "$d" || return 1
  cd "$d" && sed -i.x 's/purpose: "the name the app shows you"/purpose: "greet you by name"/' privacy/data-map.yaml && rm -f privacy/data-map.yaml.x \
    && ! python3 scripts/check_data_map.py >/dev/null && python3 scripts/check_data_map.py --write | grep -q '^wrote privacy/PRIVACY_POLICY.md$' \
    && python3 scripts/check_data_map.py && grep -q 'Greet you by name' privacy/PRIVACY_POLICY.md \
    && [ -z "$(python3 scripts/check_data_map.py --write)" ]
}
check "data map: --write regenerates the stale drafts, then the check passes and a rerun writes nothing" "_dmp_write_fixes"

# ---- packs from the risk screen (render.py, at scaffold) -----------------------------------
_dmp_render() {  # <brief.json content or ''> <expected packs line>
  local d="$T/dmp-render"; rm -rf "$d" && mkdir -p "$d/design"
  [ -n "$1" ] && printf '%s' "$1" > "$d/design/brief.json"
  python3 "$KIT/scripts/render.py" --target "$d" --name "Penny Jar" --slug penny-jar --bundle-id com.alex.pennyjar --owner alex --one-liner x >/dev/null \
    && grep -qxF "$2" "$d/privacy/data-map.yaml" && (cd "$d" && python3 scripts/check_data_map.py)
}
check "data map: render sets packs from design/brief.json risk.categories (baseline first)" \
  "_dmp_render '{\"risk\": {\"tier\": \"high\", \"categories\": [{\"id\": \"minors\", \"why\": \"kids\", \"source\": \"inferred\"}, {\"id\": \"location\", \"why\": \"map\", \"source\": \"inferred\"}]}}' 'packs: [baseline, location, minors]'"
check "data map: no risk block (or no brief) means packs: [baseline]" \
  "_dmp_render '{\"decisions\": []}' 'packs: [baseline]' && _dmp_render '' 'packs: [baseline]'"
check "data map: a category with no pack of its own adds none, and a malformed risk block is ignored" \
  "_dmp_render '{\"risk\": {\"categories\": [\"ai_decisions\", {\"id\": \"health\"}, 7]}}' 'packs: [baseline, health]' \
   && _dmp_render '{\"risk\": {\"categories\": \"minors\"}}' 'packs: [baseline]'"
_dmp_rerender_keeps_map() {  # --force never overwrites the app's map; it only refreshes packs
  local d="$T/dmp-render"; _dmp_render '' 'packs: [baseline]' || return 1
  sed -i.x 's/^  notifications: .*/  notifications: "tell you when a jar you share gets a new coin"/' "$d/privacy/data-map.yaml" && rm -f "$d/privacy/data-map.yaml.x"
  printf '%s' '{"risk": {"categories": [{"id": "financial"}]}}' > "$d/design/brief.json"
  python3 "$KIT/scripts/render.py" --target "$d" --name "Penny Jar" --slug penny-jar --bundle-id com.alex.pennyjar --owner alex --one-liner x --force >/dev/null \
    && grep -q 'a jar you share gets a new coin' "$d/privacy/data-map.yaml" && grep -qx 'packs: \[baseline, financial\]' "$d/privacy/data-map.yaml" \
    && grep -q 'a jar you share gets a new coin' "$d/privacy/PRIVACY_POLICY.md" && (cd "$d" && python3 scripts/check_data_map.py)
}
check "data map: re-render --force keeps the app's map, refreshes packs, and regenerates the drafts from it" "_dmp_rerender_keeps_map"

# ---- wiring: CI, pre-commit, the app's own tests -------------------------------------------
check "data map: CI and pre-commit run the check (not --write), and test_guards_wired knows it" \
  "grep -q 'run: python scripts/check_data_map.py$' '$APP/.github/workflows/ci.yml' \
   && grep -q 'scripts/check_data_map.py >&2' '$APP/.githooks/pre-commit' \
   && grep -q 'def test_data_map_check_runs_in_ci_and_pre_commit' '$APP/tests/harness/test_guards_wired.py'"
_dmp_wiring_plant() {  # the app's wiring test must FAIL when CI regenerates instead of checking
  local d="$T/dmp-wired"; rm -rf "$d"; mkdir -p "$d"
  (cd "$APP" && tar --exclude=node_modules --exclude=.git --exclude=.venv -cf - .github .githooks scripts tests pyproject.toml) | (cd "$d" && tar -xf -) || return 1
  sed -i.bak 's#run: python scripts/check_data_map.py#run: python scripts/check_data_map.py --write#' "$d/.github/workflows/ci.yml" && rm -f "$d/.github/workflows/ci.yml.bak"
  local out; out=$(cd "$d" && "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider tests/harness/test_guards_wired.py -k data_map_check_runs 2>&1) && return 1
  printf '%s' "$out" | grep -q "is not run by: \['ci.yml'\]"
}
_dmp_precommit() {  # the app's pre-commit refuses a staged migration whose column isn't mapped
  local d="$T/dmp-hook"; _dmp_copy "$d" || return 1
  mkdir -p "$d/.githooks" && cp "$APP/.githooks/pre-commit" "$d/.githooks/" || return 1
  cd "$d" && git init -q -b feat/x && git config core.hooksPath .githooks && git add -A \
    && git -c user.email=t@example.com -c user.name=selftest commit -qm base >/dev/null 2>&1 || return 1
  printf 'alter table public.profiles add column phone text;\n' > supabase/migrations/20990101000000_phone.sql
  git add -A
  local out; out=$(git -c user.email=t@example.com -c user.name=selftest commit -qm phone 2>&1) && return 1
  printf '%s' "$out" | grep -q 'column profiles.phone (supabase/migrations) is not in privacy/data-map.yaml' \
    && printf '%s' "$out" | grep -q 'pre-commit: privacy/data-map.yaml is incomplete'
}
check "data map: pre-commit refuses a staged migration with an unmapped column (negative control)" "_dmp_precommit"
if [ -x "$APP/.venv/bin/python" ]; then
  check "data map: test_guards_wired fails when CI regenerates instead of checking (negative control)" "_dmp_wiring_plant"
  check "data map: the app's own tests (map vs export/deletion, every rule's negative control) are green" \
    "cd '$APP' && ./.venv/bin/python -m pytest -q -p no:cacheprovider -p no:warnings tests/test_data_map.py tests/test_v1_export.py"
else
  skip "data map: test_guards_wired negative control and the app's own tests" "the app's venv"
fi
