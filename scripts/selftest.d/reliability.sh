# Reliability conventions: sourced by selftest.sh with $KIT, $APP (the rendered app, cwd),
# $T and the check/skip helpers. Four conventions in the generated backend, each green on
# a pristine render, and each guard red on a planted violation with its own message:
#   tests/test_idempotency.py    every POST under /api takes Depends(idempotent()); a
#                                replay returns the stored response (IdempotencyMiddleware)
#   tests/test_outbound_http.py  backend/http.py is the only HTTP client (timeout, retries,
#                                circuit breaker); a bare `import httpx` elsewhere fails
#   tests/test_pagination.py     Page[T] keyset pagination walks ties and inserts correctly
#   tests/test_prod_hardening.py a 429 carries RateLimit / RateLimit-Policy
# The SQL (idempotency_claim, RLS on idempotency_keys) runs in prod.sh's integration check
# and the DB gate, both against APPBOX_SELFTEST_DATABASE_URL.
RL_PT="$APP/.venv/bin/python -m pytest -q -p no:cacheprovider -p no:warnings"

# _rl_fails_with <cmd> <needle>: the command must fail AND its output must name the rule.
_rl_fails_with() {
  local out
  if out="$(eval "$1" 2>&1)"; then echo "still green"; return 1; fi
  grep -qF -- "$2" <<<"$out" || { printf '%s\n' "$out" | tail -20; echo "failed, but not on: $2"; return 1; }
}
# _rl_edit <file> <old> <new> <cmd> <needle>: replace text in a file (it must be there),
# expect the guard to fail on that needle, restore the file.
_rl_edit() {
  local rc=0
  cp "$APP/$1" "$T/rl-edit.bak"
  python3 - "$APP/$1" "$2" "$3" <<'PYEOF' || return 1
import sys
p, old, new = sys.argv[1:]
t = open(p).read()
assert old in t, f"{old!r} not in {p}"
open(p, "w").write(t.replace(old, new, 1))
PYEOF
  _rl_fails_with "$4" "$5" || rc=1
  cp "$T/rl-edit.bak" "$APP/$1"
  return "$rc"
}
RL_TESTS="tests/test_idempotency.py tests/test_outbound_http.py tests/test_pagination.py tests/test_prod_hardening.py tests/test_v1_export.py"
_rl_pt() { echo "cd '$APP' && $RL_PT $1"; }

_rl_post_without_key() {
  _rl_edit backend/routers/push.py $'        Depends(idempotent()),\n' '' "$(_rl_pt tests/test_idempotency.py)" \
    "POST routes without Depends(idempotent()): ['POST /api/v1/me/push-token']"
}
_rl_bare_httpx() {
  _rl_edit backend/routers/me.py $'import logging\n' $'import logging\n\nimport httpx  # noqa: F401\n' \
    "$(_rl_pt tests/test_outbound_http.py)" "bare HTTP client import outside backend/http.py"
}
_rl_bare_requests_in_function() {
  _rl_edit backend/services/jobs_service.py $'def iso_week(now: datetime) -> str:\n' \
    $'def iso_week(now: datetime) -> str:\n    import requests  # noqa: F401\n' \
    "$(_rl_pt tests/test_outbound_http.py)" "'backend/services/jobs_service.py': ['line"
}
_rl_store_unwired() {
  _rl_edit backend/main.py $'    app.add_middleware(IdempotencyMiddleware)\n' '' "$(_rl_pt tests/test_idempotency.py)" \
    "FAILED tests/test_idempotency.py::test_a_replay_returns_the_stored_response_without_running_again"
}
_rl_unexported() {
  _rl_edit backend/routers/export.py '    "idempotency_keys": (' '    "idempotency_keys_gone": (' \
    "$(_rl_pt tests/test_v1_export.py)" "user-owned tables missing from the data export: ['idempotency_keys']"
}
_rl_429_without_headers() {
  _rl_edit backend/ratelimit.py 'headers=limit_headers(bucket, limit, window_seconds, retry_after(window_seconds)),' \
    'headers={"Retry-After": str(retry_after(window_seconds))},' "$(_rl_pt tests/test_prod_hardening.py)" \
    "FAILED tests/test_prod_hardening.py::test_429_carries_ratelimit_and_policy_headers"
}

check "reliability: idempotency, outbound HTTP, pagination and RateLimit tests pass on a pristine render" "$(_rl_pt "$RL_TESTS")"
check "reliability catches: a POST under /api without Depends(idempotent())" "_rl_post_without_key"
check "reliability catches: a bare httpx import outside backend/http.py" "_rl_bare_httpx"
check "reliability catches: a bare requests import, even inside a function" "_rl_bare_requests_in_function"
check "reliability catches: the response store unwired (a replay runs the handler again)" "_rl_store_unwired"
check "reliability catches: idempotency_keys neither exported nor excused (the export guard sees it)" "_rl_unexported"
check "reliability catches: a 429 without its RateLimit headers" "_rl_429_without_headers"
check "reliability plants were reverted" "[ -z \"\$(git -C '$APP' status --porcelain -- backend tests)\" ]"
