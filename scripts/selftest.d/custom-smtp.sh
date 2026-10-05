# Sign-in email through custom SMTP: sourced by selftest.sh with $KIT, $APP, $T and the
# check/skip helpers. Supabase's built-in mailer allows a couple of emails an hour, so
# provision points the project at Resend (or any SMTP) and the API's production /health
# names email as unavailable until it has. Each guard passes on the pristine kit and
# FAILS on a planted violation:
#   provision SKILL.md     documents the setup and never expands a secret in a command
#   supabase_smtp.py       sends the Management API PATCH, never prints the key
#   backend/config.py      production /health names "email sign-in (custom SMTP)"
SMTP_PY="$KIT/scripts/supabase_smtp.py"
PROV="$KIT/skills/provision/SKILL.md"
SMTP_SECRET="re_selftest_planted_$$_9f8e7d6c"   # a key-shaped value that must never appear
SMTP_REF="abcdefghijklmnopqrst"

check "smtp: provision documents Resend + any-SMTP setup through the script and the Management API" \
  "grep -q 'Resend' '$PROV' && grep -q 'recommended' '$PROV' && grep -q 'Another SMTP' '$PROV' \
   && grep -q 'scripts/supabase_smtp.py\" --ref' '$PROV' && grep -q -- '--host <host> --port' '$PROV' \
   && grep -q 'PATCH /v1/projects/<ref>/config/auth' '$PROV' && grep -q 'AUTH_SMTP_HOST' '$PROV' \
   && grep -q 'pass = \"env(SMTP_PASS)\"' '$PROV' && grep -q '\[auth.email.smtp\]' '$PROV'"
check "smtp: the script's Resend preset is what the docs say (smtp.resend.com, 465, user resend)" \
  "grep -q '\"host\": \"smtp.resend.com\", \"port\": \"465\", \"user\": \"resend\"' '$SMTP_PY'"
check "smtp: PRODUCTION.md, RELEASING.md and the app's release runbook carry it on the launch checklist" \
  "grep -q 'Sign-in email through custom SMTP' '$KIT/docs/PRODUCTION.md' \
   && grep -q 'Sign-in email (Resend free tier)' '$KIT/../../RELEASING.md' \
   && grep -q 'Sign-in email goes through custom SMTP' '$KIT/template/docs/runbooks/release.md'"

# The provision text must never put a secret on a command line: no `$SMTP_PASS` or
# `$SUPABASE_ACCESS_TOKEN` expansion (echo, curl -d, --pass, gh secret set...). Only
# supabase_smtp.py reads them, from its environment.
_smtp_no_expansion() {  # <skill file>: prints each offending line and fails
  local hits
  hits=$(grep -nE '\$\{?(SMTP_PASS|SUPABASE_ACCESS_TOKEN|RESEND_API_KEY)\b' "$1") || return 0
  printf 'provision expands an SMTP secret in a command:\n%s\n' "$hits"; return 1
}
_smtp_plant() {  # <line to append> : the guard must fail on it, naming it
  cp "$PROV" "$T/prov-smtp.md" && printf '%s\n' "$1" >> "$T/prov-smtp.md"
  local out; out=$(_smtp_no_expansion "$T/prov-smtp.md") && return 1
  printf '%s' "$out" | grep -q 'provision expands an SMTP secret in a command' && printf '%s' "$out" | grep -qF "$1"
}
check "smtp: provision never expands the SMTP key or the access token in a command" "_smtp_no_expansion '$PROV'"
check "smtp guard catches: an echoed key (negative control)" "_smtp_plant 'set -a; . ./.env; set +a; echo \"\$SMTP_PASS\"'"
check "smtp guard catches: the key in a curl body (negative control)" \
  "_smtp_plant 'curl -X PATCH https://api.supabase.com/v1/projects/x/config/auth -d \"{\\\"smtp_pass\\\":\\\"\${SMTP_PASS}\\\"}\"'"

# The script itself, with a planted key: dry run, refusals, and a real PATCH against a
# local stand-in for the Management API (it records what it got; ref "failfailfail"
# answers 400 and echoes the body back, as a careless API error might).
check "smtp script: dry run shows the request and redacts the key and the token" \
  "out=\$(SMTP_PASS='$SMTP_SECRET' SUPABASE_ACCESS_TOKEN='sbp_$SMTP_SECRET' python3 '$SMTP_PY' --ref $SMTP_REF --resend --sender-email no-reply@pennyjar.app --sender-name 'Penny Jar' --dry-run 2>&1) \
   && printf '%s' \"\$out\" | grep -q '\"smtp_host\": \"smtp.resend.com\"' && printf '%s' \"\$out\" | grep -q '\"smtp_port\": \"465\"' \
   && printf '%s' \"\$out\" | grep -q '\"smtp_pass\": \"\*\*\*' && ! printf '%s' \"\$out\" | grep -q '$SMTP_SECRET'"
check "smtp script refuses: missing SMTP_PASS (exit 2, named) and a key passed as an argument" \
  "out=\$(env -u SMTP_PASS SUPABASE_ACCESS_TOKEN=x python3 '$SMTP_PY' --ref $SMTP_REF --resend --sender-email a@b.co --sender-name X 2>&1); [ \$? -eq 2 ] \
   && printf '%s' \"\$out\" | grep -q 'SMTP_PASS not set' \
   && { python3 '$SMTP_PY' --ref $SMTP_REF --resend --sender-email a@b.co --sender-name X --pass '$SMTP_SECRET' >/dev/null 2>&1; [ \$? -eq 2 ]; }"

_smtp_server() {  # starts the stand-in API; sets SMTP_API and SMTP_SRV_PID
  cat > "$T/smtp_api.py" <<'PYEOF'
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
log = sys.argv[1]
class H(BaseHTTPRequestHandler):
    def do_PATCH(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        json.dump({"path": self.path, "auth": self.headers["Authorization"], "body": json.loads(body)}, open(log, "w"))
        bad = "failfailfail" in self.path
        self.send_response(400 if bad else 200); self.end_headers()
        self.wfile.write((("bad request: " + body) if bad else "{}").encode())
    def log_message(self, *a): pass
s = HTTPServer(("127.0.0.1", 0), H)
open(log + ".port", "w").write(str(s.server_address[1]))
s.serve_forever()
PYEOF
  rm -f "$T/smtp_api.log" "$T/smtp_api.log.port"
  python3 "$T/smtp_api.py" "$T/smtp_api.log" & SMTP_SRV_PID=$!
  local i; for i in $(seq 50); do [ -s "$T/smtp_api.log.port" ] && break; sleep 0.1; done
  SMTP_API="http://127.0.0.1:$(cat "$T/smtp_api.log.port")"
}
_smtp_patch_ok() {
  _smtp_server; local rc=0 out err
  : > "$T/smtp.env"
  out=$(SMTP_PASS="$SMTP_SECRET" SUPABASE_ACCESS_TOKEN="sbp_tok" python3 "$SMTP_PY" --api "$SMTP_API" --ref $SMTP_REF --resend \
        --sender-email no-reply@pennyjar.app --sender-name "Penny Jar" 2>"$T/smtp.err") || rc=1
  err=$(cat "$T/smtp.err")
  [ "$rc" = 0 ] && [ "$out" = "AUTH_SMTP_HOST=smtp.resend.com" ] || rc=1
  printf '%s\n' "$out" | python3 "$KIT/scripts/env_set.py" "$T/smtp.env" >/dev/null && grep -qx 'AUTH_SMTP_HOST=smtp.resend.com' "$T/smtp.env" || rc=1
  printf '%s%s' "$out" "$err" | grep -q "$SMTP_SECRET" && rc=1
  python3 - "$T/smtp_api.log" "$SMTP_SECRET" <<'PYEOF' || rc=1
import json, sys
got = json.load(open(sys.argv[1])); b = got["body"]
assert got["path"] == "/v1/projects/abcdefghijklmnopqrst/config/auth", got["path"]
assert got["auth"] == "Bearer sbp_tok"
assert b["smtp_host"] == "smtp.resend.com" and b["smtp_port"] == "465" and b["smtp_user"] == "resend"
assert b["smtp_pass"] == sys.argv[2] and b["smtp_admin_email"] == "no-reply@pennyjar.app"
assert b["smtp_sender_name"] == "Penny Jar" and b["external_email_enabled"] is True
PYEOF
  kill "$SMTP_SRV_PID" 2>/dev/null; wait "$SMTP_SRV_PID" 2>/dev/null
  return $rc
}
_smtp_patch_error_scrubbed() {
  _smtp_server; local rc=0 out
  out=$(SMTP_PASS="$SMTP_SECRET" SUPABASE_ACCESS_TOKEN="sbp_tok" python3 "$SMTP_PY" --api "$SMTP_API" --ref failfailfail --resend \
        --sender-email no-reply@pennyjar.app --sender-name "Penny Jar" 2>&1) && rc=1
  printf '%s' "$out" | grep -q 'Supabase answered 400' || rc=1
  printf '%s' "$out" | grep -q '"smtp_pass": "\*\*\*"' || rc=1     # the echo arrived, scrubbed
  printf '%s' "$out" | grep -q "$SMTP_SECRET" && rc=1
  kill "$SMTP_SRV_PID" 2>/dev/null; wait "$SMTP_SRV_PID" 2>/dev/null
  return $rc
}
check "smtp script: PATCHes config/auth with the Management API's smtp_* fields; stdout is only the marker" "_smtp_patch_ok"
check "smtp script: an API error that echoes the request back is shown with the key scrubbed" "_smtp_patch_error_scrubbed"

# The API side, in the rendered app: production /health names email until the marker
# is set, and never outside production (local `supabase start` catches mail itself).
_smtp_health() {  # <env assignments...> -> prints the features_unavailable JSON
  (cd "$APP" && env -u AUTH_SMTP_HOST -u SENTRY_DSN "$@" ./.venv/bin/python -c "
import json; from fastapi.testclient import TestClient; from backend.main import create_app
print(json.dumps(TestClient(create_app()).get('/health').json().get('features_unavailable', {})))")
}
if [ -x "$APP/.venv/bin/python" ]; then
  check "smtp health: production with no SMTP names 'email sign-in (custom SMTP)' (planted missing config)" \
    "_smtp_health APP_ENV=production SUPABASE_URL=x SUPABASE_SECRET_KEY=x | grep -q '\"email sign-in (custom SMTP)\": \[\"AUTH_SMTP_HOST\"\]'"
  check "smtp health: production with AUTH_SMTP_HOST set stops naming email, and Supabase stays separate" \
    "out=\$(_smtp_health APP_ENV=production AUTH_SMTP_HOST=smtp.resend.com) && ! printf '%s' \"\$out\" | grep -q 'email sign-in' && printf '%s' \"\$out\" | grep -q 'database + auth'"
  check "smtp health: outside production email isn't required" \
    "out=\$(_smtp_health APP_ENV=development SUPABASE_URL=x SUPABASE_SECRET_KEY=x) && ! printf '%s' \"\$out\" | grep -q 'email sign-in'"
else
  skip "smtp health: production /health names email (needs the rendered app's venv)" "venv"
fi
