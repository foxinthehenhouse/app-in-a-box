# Safer migrations: sourced by selftest.sh with $KIT, $APP (the rendered app, cwd), $T
# and the check/skip helpers. Two guards in the generated repo's DB workflow, each
# proven green on a pristine render AND red on a planted violation:
#   scripts/db-lint.sh   squawk (pinned) on every migration, rules in .squawk.toml, with
#                        its own negative control (planted unsafe migrations)
#   scripts/db-test.sh   step 7: the migrated schema must match the committed
#                        supabase/schema-snapshot.txt (needs a throwaway Postgres)
# The squawk checks need `squawk` on PATH at the pinned version (kit CI installs it);
# the drift check needs APPBOX_SELFTEST_DATABASE_URL. Otherwise each is a visible SKIP.
SM_PY="$APP/.venv/bin/python"
SM_PT="$SM_PY -m pytest -q -p no:cacheprovider -p no:warnings"
SM_PIN="$(sed -n 's/^SQUAWK_VERSION="\(.*\)"$/\1/p' "$APP/scripts/db-lint.sh")"
SM_PLANT="$APP/supabase/migrations/20990101000000_planted.sql"

# _sm_fails_with <cmd> <needle>: the command must fail AND its output must name the rule.
_sm_fails_with() {
  local out
  if out="$(eval "$1" 2>&1)"; then echo "still green"; return 1; fi
  grep -qF -- "$2" <<<"$out" || { printf '%s\n' "$out" | tail -20; echo "failed, but not on: $2"; return 1; }
}
# _sm_plant <sql> <needle>: a planted migration must fail db-lint on that rule.
_sm_plant() {
  local rc=0
  printf -- '-- Rollback: none, planted by the selftest.\n%s\n' "$1" > "$SM_PLANT"
  _sm_fails_with "cd '$APP' && scripts/db-lint.sh" "$2" || rc=1
  rm -f "$SM_PLANT"
  return "$rc"
}
# _sm_edit <file> <old> <new> <cmd> <needle>: replace text in a file (it must be there),
# expect the guard to fail on that needle, restore the file.
_sm_edit() {
  local rc=0
  cp "$APP/$1" "$T/sm-edit.bak"
  python3 - "$APP/$1" "$2" "$3" <<'PYEOF' || return 1
import sys
p, old, new = sys.argv[1:]
t = open(p).read()
assert old in t, f"{old!r} not in {p}"
open(p, "w").write(t.replace(old, new))
PYEOF
  _sm_fails_with "$4" "$5" || rc=1
  cp "$T/sm-edit.bak" "$APP/$1"
  return "$rc"
}
SM_EXCL_OLD='excluded_rules = ['
SM_EXCL_NEW='excluded_rules = [ "renaming-column",'

check "migration lint: squawk config present and db.yml runs scripts/db-lint.sh" \
  "[ -f '$APP/.squawk.toml' ] && grep -q 'run: scripts/db-lint.sh' '$APP/.github/workflows/db.yml' && [ -x '$APP/scripts/db-lint.sh' ]"
check "migration lint: squawk is pinned, and kit CI installs that same version" \
  "[ -n '$SM_PIN' ] && grep -q \"SQUAWK_VERSION: \\\"$SM_PIN\\\"\" '$KIT/../../.github/workflows/kit.yml'"
check "migration lint: the guard-wiring and config tests pass on a pristine render" \
  "cd '$APP' && $SM_PT tests/harness/test_guards_wired.py"
check "migration lint catches: db.yml no longer running db-lint.sh (guard-wiring test)" \
  "_sm_edit .github/workflows/db.yml 'run: scripts/db-lint.sh' 'run: echo skipped' \
   \"cd '$APP' && $SM_PT tests/harness/test_guards_wired.py\" 'no longer runs the migration linter'"
check "migration lint catches: a live-database rule switched off in .squawk.toml" \
  "_sm_edit .squawk.toml \"\$SM_EXCL_OLD\" \"\$SM_EXCL_NEW\" \
   \"cd '$APP' && $SM_PT tests/harness/test_guards_wired.py\" 'renaming-column must stay on'"
check "the db-migrations rule teaches expand/contract" \
  "grep -q 'Expand, then contract' '$APP/.agents/rules/db-migrations.md' && grep -q 'Never drop or rename a column' '$APP/.agents/rules/db-migrations.md'"

if command -v squawk >/dev/null 2>&1 && [ "$(squawk --version 2>/dev/null)" = "squawk $SM_PIN" ]; then
  check "migration lint: squawk green on the template's migrations (and its negative control)" \
    "cd '$APP' && scripts/db-lint.sh"
  check "migration lint catches: CREATE INDEX without CONCURRENTLY on an existing table" \
    "_sm_plant 'create index profiles_created_idx on public.profiles (created_at);' 'require-concurrent-index-creation'"
  check "migration lint catches: ADD COLUMN NOT NULL with no default" \
    "_sm_plant 'alter table public.profiles add column plan text not null;' 'adding-required-field'"
  check "migration lint catches: a column rename" \
    "_sm_plant 'alter table public.profiles rename column display_name to name;' 'renaming-column'"
  check "migration lint catches: a dropped column" \
    "_sm_plant 'alter table public.profiles drop column display_name;' 'ban-drop-column'"
  check "migration lint allows: an index on a table created in the same migration" \
    "printf -- '-- Rollback: drop table public.planted;\ncreate table public.planted (id bigint primary key);\ncreate index planted_id_idx on public.planted (id);\n' > '$SM_PLANT' \
     && (cd '$APP' && scripts/db-lint.sh); rc=\$?; rm -f '$SM_PLANT'; exit \$rc"
  # The linter's own negative control: with the rule switched off it must say it is blind.
  check "migration lint: its negative control fails when the rule it plants for is off" \
    "_sm_edit .squawk.toml \"\$SM_EXCL_OLD\" \"\$SM_EXCL_NEW\" \
     \"cd '$APP' && scripts/db-lint.sh\" 'squawk passed a planted rename migration; the linter is blind'"
else
  skip "migration lint: squawk on the migrations + planted unsafe migrations" "squawk $SM_PIN (npm i -g squawk-cli@$SM_PIN)"
fi

if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ]; then
  # A database of our own, so the plant can't leave anything in the one the DB gate uses.
  SM_DB="appbox_sm_$$"
  SM_URL="${APPBOX_SELFTEST_DATABASE_URL%/*}/$SM_DB"
  _sm_drift() {
    local rc=0
    psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "create database $SM_DB" || return 1
    printf -- '-- Rollback: alter table public.profiles drop column plan;\nalter table public.profiles add column plan text;\n' > "$SM_PLANT"
    _sm_fails_with "cd '$APP' && DATABASE_URL='$SM_URL' scripts/db-test.sh" \
      "::error file=supabase/schema-snapshot.txt::the migrations produce a different schema" || rc=1
    rm -f "$SM_PLANT"
    psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "drop database if exists $SM_DB with (force)" || rc=1
    return "$rc"
  }
  check "schema drift: a migration not reflected in supabase/schema-snapshot.txt fails the DB gate" "_sm_drift"
else
  skip "schema drift: planted migration vs supabase/schema-snapshot.txt" "APPBOX_SELFTEST_DATABASE_URL (Postgres + pgTAP)"
fi
check "migration plants were reverted" "[ -z \"\$(git -C '$APP' status --porcelain -- supabase .squawk.toml .github)\" ]"
