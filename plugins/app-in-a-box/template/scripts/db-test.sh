#!/usr/bin/env bash
# Database gate: apply every migration to a THROWAWAY Postgres and prove RLS holds.
# Run by .github/workflows/db.yml on every PR that touches supabase/; runs locally too.
#
#   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres scripts/db-test.sh
#
# Against a local Supabase stack (`supabase start`), point it at the stack's DB
# (postgresql://postgres:postgres@127.0.0.1:54322/postgres); the platform stubs are
# skipped because auth.users already exists. Needs psql and the pgTAP extension.
#
# Steps, each of which fails the run:
#   1. migration versions unique and well-formed (scripts/check_migration_versions.py)
#   2. Supabase platform stubs, only if auth.users is absent (supabase/ci/platform_stubs.sql)
#   3. every supabase/migrations/*.sql applied in filename order, ON_ERROR_STOP
#   4. advisors: no ERROR rows from supabase/ci/advisors.sql
#   5. pgTAP: every supabase/tests/**/*.test.sql passes
#   6. negative control: with supabase/ci/negative_control.sql planted (rolled back),
#      steps 4 and 5 MUST fail. If they stay green the gate is blind, and this fails.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${DATABASE_URL:?set DATABASE_URL to a THROWAWAY Postgres superuser connection}"
case "$DATABASE_URL" in
  *supabase.co*|*supabase.com*|*pooler.supabase*)
    echo "db-test: refusing a hosted Supabase URL. This script creates and drops objects." >&2
    exit 2 ;;
esac
PSQL=(psql "$DATABASE_URL" -X -q -v ON_ERROR_STOP=1)
fail=0
say() { printf '\n== %s\n' "$*"; }

say "1. migration versions"
python3 scripts/check_migration_versions.py

say "2. platform stubs"
if [ "$("${PSQL[@]}" -tAc "select to_regclass('auth.users') is null")" = "t" ]; then
  "${PSQL[@]}" -f supabase/ci/platform_stubs.sql
  echo "applied supabase/ci/platform_stubs.sql (plain Postgres)"
else
  echo "auth.users exists: a real Supabase stack, stubs skipped"
fi

say "3. migrations"
n=0; failed=()
while IFS= read -r f; do
  if "${PSQL[@]}" -f "$f"; then n=$((n + 1)); else failed+=("$f"); fi
done < <(find supabase/migrations -maxdepth 1 -name '*.sql' | LC_ALL=C sort)
echo "applied $n, failed ${#failed[@]}"
for f in ${failed[@]+"${failed[@]}"}; do echo "::error file=$f::migration failed to apply on a fresh database"; done
[ "${#failed[@]}" -eq 0 ] && [ "$n" -gt 0 ] || exit 1

# pgTAP lives in its own `extensions` schema, as on Supabase, so its helper views don't
# show up in public (and in the advisors). New sessions get it on the search_path.
"${PSQL[@]}" -f supabase/ci/pgtap.sql \
  || { echo "db-test: the pgTAP extension is not installed (apt: postgresql-<ver>-pgtap)" >&2; exit 1; }

# run_sql <prelude-file> <sql-file>...: one psql session, tuples-only, errors kept in the
# output (a test that errors must show up as a failure, not abort the report).
run_sql() {
  local prelude="$1"; shift
  cat "$prelude" "$@" | psql "$DATABASE_URL" -X -q -tA -F'|' -v ON_ERROR_STOP=0 2>&1
}
# Every pgTAP file wraps itself in begin/rollback; a prelude that opens a transaction
# first (the negative control) is rolled back by the file's own `rollback`.
pgtap() {
  local f out=""
  while IFS= read -r f; do
    out+="# $f"$'\n'"$(run_sql "$1" "$f")"$'\n'
  done < <(find supabase/tests -name '*.test.sql' | LC_ALL=C sort)
  printf '%s' "$out"
}
tap_failed() { grep -Eq '^not ok|# Looks like you (failed|planned)|ERROR:' <<<"$1"; }
tap_count() { grep -Ec '^ok ' <<<"$1" || true; }
TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT
: > "$TMPD/none.sql"
{ echo "begin;"; cat supabase/ci/negative_control.sql; } > "$TMPD/plant.sql"
echo "rollback;" > "$TMPD/rollback.sql"

say "4. advisors"
report="$(run_sql "$TMPD/none.sql" supabase/ci/advisors.sql)"
[ -z "$report" ] || printf '%s\n' "$report"
if grep -Eq '^ERROR' <<<"$report"; then
  echo "::error::Supabase advisors report ERROR-level issues (see above)"; fail=1
else
  echo "no ERROR-level advisor findings"
fi

say "5. pgTAP"
tap="$(pgtap "$TMPD/none.sql")"
printf '%s\n' "$tap"
if tap_failed "$tap" || [ "$(tap_count "$tap")" -eq 0 ]; then
  echo "::error::pgTAP RLS tests failed"; fail=1
else
  echo "pgTAP: $(tap_count "$tap") assertions passed"
fi

say "6. negative control (planted RLS holes must be caught)"
neg_adv="$(run_sql "$TMPD/plant.sql" supabase/ci/advisors.sql "$TMPD/rollback.sql")"
if grep -q '^ERROR|rls_disabled_in_public|public.negctl_unprotected' <<<"$neg_adv" \
   && grep -q '^ERROR|function_search_path_mutable|public.negctl_definer' <<<"$neg_adv"; then
  echo "advisors caught the planted table without RLS and the mutable-search_path function"
else
  printf '%s\n' "$neg_adv"
  echo "::error::advisors did NOT catch the planted issues; the advisor gate is blind"; fail=1
fi
neg_tap="$(pgtap "$TMPD/plant.sql")"
if grep -q '^not ok' <<<"$neg_tap"; then
  echo "pgTAP caught the planted over-broad policies ($(grep -c '^not ok' <<<"$neg_tap") failing assertions)"
else
  printf '%s\n' "$neg_tap"
  echo "::error::pgTAP stayed green with RLS holes planted; the RLS tests are blind"; fail=1
fi
# The negative control must leave nothing behind.
[ "$("${PSQL[@]}" -tAc "select count(*) from pg_class where relname = 'negctl_unprotected'")" = "0" ] \
  || { echo "::error::negative control leaked into the database"; fail=1; }

say "result"
if [ "$fail" -eq 0 ]; then echo "db-test: all green"; else echo "db-test: FAILED"; fi
exit "$fail"
