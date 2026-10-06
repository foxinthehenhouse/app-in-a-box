# Audit trail + account erasure: sourced by selftest.sh with $KIT, $APP (the rendered
# app, cwd), $T and the check/skip helpers. Each guard is proven green on a pristine
# render AND red on a planted violation, with the message that names it:
#   tests/test_audit_events.py   deletion + export each write an audit row, fail closed
#   tests/test_erasure.py        deletion empties Storage, PostHog, Sentry (fakes only),
#                                vendors are no-ops when unset, and every bucket a
#                                migration creates is purged or explained
#   tests/test_v1_export.py      the export includes the caller's audit rows, scoped
#   supabase/tests/database/audit_events.test.sql   append-only + service-role-only,
#                                against a real Postgres (needs APPBOX_SELFTEST_DATABASE_URL)
AG_PT="$APP/.venv/bin/python -m pytest -q -p no:cacheprovider -p no:warnings"
AG_TESTS="tests/test_audit_events.py tests/test_erasure.py tests/test_v1_export.py tests/test_prod_account_deletion.py tests/test_scoping_static.py"
AG_PLANT="$APP/supabase/migrations/20990101000000_planted.sql"

# _ag_fails_with <cmd> <needle>: the command must fail AND its output must name the rule.
_ag_fails_with() {
  local out
  if out="$(eval "$1" 2>&1)"; then echo "still green"; return 1; fi
  grep -qF -- "$2" <<<"$out" || { printf '%s\n' "$out" | tail -20; echo "failed, but not on: $2"; return 1; }
}
# _ag_edit <file> <old> <new> <tests> <needle>: replace text in an app file (it must be
# there), expect those tests to fail on the needle, restore the file.
_ag_edit() {
  local rc=0
  cp "$APP/$1" "$T/ag-edit.bak"
  python3 - "$APP/$1" "$2" "$3" <<'PYEOF' || return 1
import sys
p, old, new = sys.argv[1:]
t = open(p).read()
assert old in t, f"{old!r} not in {p}"
open(p, "w").write(t.replace(old, new))
PYEOF
  _ag_fails_with "cd '$APP' && $AG_PT $4" "$5" || rc=1
  cp "$T/ag-edit.bak" "$APP/$1"
  return "$rc"
}

check "audit + erasure: the tests pass on a pristine render" "cd '$APP' && $AG_PT $AG_TESTS"

# Audit rows on the sensitive endpoints.
check "audit catches: account deletion that no longer writes its audit row" \
  "_ag_edit backend/routers/me.py 'audit_service.record(db, user.id, \"account.delete\")' 'None' \
   tests/test_audit_events.py 'FAILED tests/test_audit_events.py::test_account_delete_does_not_happen_without_its_audit_row'"
check "audit catches: an export that no longer writes its audit row" \
  "_ag_edit backend/routers/export.py 'audit_service.record(db, user.id, \"data.export\")' 'None' \
   tests/test_audit_events.py 'FAILED tests/test_audit_events.py::test_export_is_audited'"
check "audit catches: a vendor failure that is no longer written to the trail" \
  "_ag_edit backend/routers/me.py 'audit_service.record(db, user_id, \"account.erasure_failed\", target=vendor)' 'pass' \
   tests/test_erasure.py 'FAILED tests/test_erasure.py::test_a_vendor_outage_does_not_block_deletion_and_is_audited'"

# The export includes the trail, scoped to the caller.
check "export catches: audit_events dropped from the export" \
  "_ag_edit backend/routers/export.py '    \"audit_events\": _read_audit_events,' '' \
   tests/test_v1_export.py 'FAILED tests/test_v1_export.py::test_exports_the_callers_rows_in_every_table'"
check "export catches: the audit reader filtering by something other than the caller" \
  "_ag_edit backend/routers/export.py '.eq(\"actor_id\", user_id)' '.eq(\"action\", \"data.export\")' \
   tests/test_scoping_static.py 'backend/routers/export.py:_read_audit_events'"

# Erasure fan-out.
check "erasure catches: deletion that no longer empties the user's Storage" \
  "_ag_edit backend/routers/me.py '    erasure_service.purge_storage(db, user.id)' '    pass' \
   tests/test_erasure.py 'FAILED tests/test_erasure.py::test_delete_erases_storage_posthog_and_sentry'"
check "erasure catches: deletion that no longer deletes the PostHog person" \
  "_ag_edit backend/routers/me.py '(\"posthog\", erasure_service.delete_posthog_person),' '' \
   tests/test_erasure.py 'FAILED tests/test_erasure.py::test_delete_erases_storage_posthog_and_sentry'"
check "erasure catches: deletion that no longer purges Sentry" \
  "_ag_edit backend/routers/me.py '(\"sentry\", erasure_service.purge_sentry_user),' '' \
   tests/test_erasure.py 'FAILED tests/test_erasure.py::test_delete_erases_storage_posthog_and_sentry'"
check "erasure catches: a vendor call that no longer checks its own feature config" \
  "_ag_edit backend/services/erasure_service.py 'if feature_missing(POSTHOG_FEATURE):' 'if False:' \
   tests/test_erasure.py 'unconfigured erasure made a request'"
check "erasure catches: a Storage bucket a migration creates that deletion doesn't empty" \
  "printf -- \"-- Rollback: delete from storage.buckets where id = 'avatars';\ninsert into storage.buckets (id, name, public) values ('avatars', 'avatars', false);\n\" > '$AG_PLANT' \
   && _ag_fails_with \"cd '$APP' && $AG_PT tests/test_erasure.py\" \"storage buckets that account deletion doesn't empty: ['avatars']\"; \
   rc=\$?; rm -f '$AG_PLANT'; exit \$rc"
check "erasure allows: that bucket once it is listed for purging" \
  "printf -- \"-- Rollback: delete from storage.buckets where id = 'avatars';\ninsert into storage.buckets (id, name, public) values ('avatars', 'avatars', false);\n\" > '$AG_PLANT' \
   && cp '$APP/backend/services/erasure_service.py' '$T/ag-es.bak' \
   && sed -i.sed 's/^USER_FILE_BUCKETS: tuple\[str, ...\] = ()/USER_FILE_BUCKETS: tuple[str, ...] = (\"avatars\",)/' '$APP/backend/services/erasure_service.py' \
   && (cd '$APP' && $AG_PT tests/test_erasure.py); \
   rc=\$?; rm -f '$AG_PLANT' '$APP/backend/services/erasure_service.py.sed'; cp '$T/ag-es.bak' '$APP/backend/services/erasure_service.py'; exit \$rc"

check "audit + erasure: dormant vendors are optional features, not degraded /health" \
  "cd '$APP' && ./.venv/bin/python -c \"from backend.config import OPTIONAL_FEATURE_CONFIG as o, FEATURE_CONFIG as f; assert 'account erasure: PostHog' in o and 'account erasure: Sentry' in o and not any(k.startswith('account erasure') for k in f)\""

# The table itself, against a real Postgres: the pgTAP suite must fail when either wall
# of the append-only table is knocked down by a later migration.
if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ]; then
  _ag_db() {  # <planted migration body> <needle>: fresh database, plant, db-test must fail on it
    local rc=0 db="appbox_ag_$$_$RANDOM"
    local url="${APPBOX_SELFTEST_DATABASE_URL%/*}/$db"
    psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "create database $db" || return 1
    printf -- '-- Rollback: none, planted by the selftest.\n%s\n' "$1" > "$AG_PLANT"
    _ag_fails_with "cd '$APP' && DATABASE_URL='$url' scripts/db-test.sh" "$2" || rc=1
    rm -f "$AG_PLANT"
    psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "drop database if exists $db with (force)" || rc=1
    return "$rc"
  }
  check "audit table catches: the append-only trigger dropped (pgTAP)" \
    "_ag_db 'drop trigger audit_events_no_update_delete on public.audit_events;' 'not ok 1 - audit_events: an update is refused, even for the superuser'"
  check "audit table catches: the service role given update/delete back (pgTAP)" \
    "_ag_db 'grant update, delete on public.audit_events to service_role;' 'not ok 7 - audit_events: the service role holds no update grant'"
  check "audit table catches: the trail opened to signed-in users (pgTAP)" \
    "_ag_db 'grant select on public.audit_events to authenticated; create policy audit_open on public.audit_events for select using (true);' 'not ok 9 - audit_events: a signed-in user cannot read the trail'"
else
  skip "audit table: append-only + service-role-only plants against pgTAP" "APPBOX_SELFTEST_DATABASE_URL (Postgres + pgTAP)"
fi
check "audit + erasure plants were reverted" "[ -z \"\$(git -C '$APP' status --porcelain -- backend supabase tests)\" ]"
