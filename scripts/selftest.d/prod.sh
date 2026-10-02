# Production backend (v1.0): sourced by selftest.sh with $APP, $KIT, $T and
# the check/refuses helpers. Proves the new tests pass in the rendered app, the cron
# endpoint fails closed, trailing slashes never redirect, and each guard's test FAILS
# when the guard is removed (a guard that can't fail reads as a guard that passes).
#
# With APPBOX_SELFTEST_DATABASE_URL=<throwaway Postgres> (the same variable trust.sh and
# kit CI use) the migrations are applied and the SQL functions exercised for real
# (tests/test_prod_migrations.py -m integration); otherwise that check is a visible SKIP.

PROD_PY="$APP/.venv/bin/python"

check "prod tests green (tests/test_prod_*.py)" "cd '$APP' && '$PROD_PY' -m pytest -q -p no:warnings tests/test_prod_*.py"
check "cron endpoint 503s without CRON_SECRET" "cd '$APP' && env -u CRON_SECRET '$PROD_PY' -c \"from fastapi.testclient import TestClient; from backend.main import create_app; r = TestClient(create_app()).post('/internal/cron/weekly-digest', headers={'X-Cron-Secret': 'x' * 40}); assert r.status_code == 503, r.status_code\""
check "redirect_slashes off (no 307 that drops auth)" "cd '$APP' && '$PROD_PY' -c \"from fastapi.testclient import TestClient; from backend.main import create_app; r = TestClient(create_app()).get('/api/v1/me/', follow_redirects=False); assert r.status_code == 404, r.status_code\""

# name, file (relative to $APP), sed expression, test file
_prod_negative() {
  cp "$APP/$2" "$T/prod-neg.bak"
  sed -i.sedbak "$3" "$APP/$2" && rm -f "$APP/$2.sedbak"
  if cmp -s "$T/prod-neg.bak" "$APP/$2"; then
    bad "$1 (planted change did not apply; update prod.sh)"
  else
    refuses "$1" "cd '$APP' && '$PROD_PY' -m pytest -q -x -p no:warnings $4" "FAILED tests/"
  fi
  cp "$T/prod-neg.bak" "$APP/$2"
}

_prod_negative "push-token delete test fails when user scoping is removed" \
  backend/routers/push.py 's/\.eq("user_id", user\.id)\.eq("token"/.eq("token"/' tests/test_prod_push.py
_prod_negative "push send test fails when token read is unscoped" \
  backend/services/push_service.py 's/select("token")\.eq("user_id", user_id)/select("token")/' tests/test_prod_push.py
_prod_negative "cron tests fail when the secret check is removed" \
  backend/routers/internal.py 's/dependencies=\[Depends(require_cron_secret)\]/dependencies=[]/' tests/test_prod_cron.py
_prod_negative "cron tests fail when the secret may be short" \
  backend/routers/internal.py 's/CRON_SECRET_MIN_LENGTH = 32/CRON_SECRET_MIN_LENGTH = 1/' tests/test_prod_cron.py
_prod_negative "rate-limit tests fail when the limit is not enforced" \
  backend/ratelimit.py 's/if count > limit:/if False:/' tests/test_prod_hardening.py
_prod_negative "slash test fails when redirect_slashes is back on" \
  backend/main.py 's/redirect_slashes=False/redirect_slashes=True/' tests/test_prod_hardening.py
_prod_negative "deletion tests fail when extra body fields are accepted" \
  backend/routers/me.py 's/, extra="forbid"//' tests/test_prod_account_deletion.py
_prod_negative "RLS rule fails on a table without RLS" \
  supabase/migrations/20260315120100_rate_limits_and_jobs.sql 's/^alter table public\.job_runs enable row level security;//' tests/test_prod_migrations.py

if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ]; then
  check "migrations apply + SQL functions behave (real Postgres)" "cd '$APP' && DATABASE_URL='$APPBOX_SELFTEST_DATABASE_URL' '$PROD_PY' -m pytest -q -p no:warnings -m integration tests/test_prod_migrations.py"
else
  skip "migrations apply + SQL functions behave (real Postgres)" "APPBOX_SELFTEST_DATABASE_URL (Postgres + pgTAP)"
fi
