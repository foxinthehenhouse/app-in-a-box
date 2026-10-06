# Ops defaults: sourced by selftest.sh with $KIT, $APP, $T and the check/skip helpers.
# Provision ends with an uptime monitor on /health, nightly age-encrypted backups with a
# restore drill, and a spend-cap checklist in the app's COST.md. Each guard passes on the
# pristine kit and FAILS on a planted violation:
#   provision SKILL.md       documents all three, never prints a backup secret or the key
#   uptime_monitor.py        creates (or reuses) the monitor, never prints the token
#   tests/test_backup.py     (app) the backup can't print a secret or hold a private key
#   backup-db.sh + restore-drill.sh   a real round trip: Postgres -> age -> bucket -> restore
echo "Ops defaults"
OPS_PROV="$KIT/skills/provision/SKILL.md"
OPS_UP="$KIT/scripts/uptime_monitor.py"
OPS_PY="$APP/.venv/bin/python"
OPS_TOKEN="bst_planted_$$_4c3b2a19"            # token-shaped values that must never appear
OPS_DB_PW="dbpw-planted-$$-e5f6a7b8"
OPS_S3_KEY="s3key-planted-$$-0a1b2c3d"

check "ops: provision step 8 covers the uptime monitor, nightly backups and spend caps" \
  "grep -q '^## 8. Ops defaults: uptime monitor, nightly backups, spend caps' '$OPS_PROV' \
   && grep -q 'scripts/uptime_monitor.py\" --provider betterstack' '$OPS_PROV' && grep -q -- '--provider sentry' '$OPS_PROV' \
   && grep -q 'backup.yml' '$OPS_PROV' && grep -q 'age-keygen -y' '$OPS_PROV' && grep -q 'Session' '$OPS_PROV' \
   && grep -q 'gh variable set BACKUP_AGE_RECIPIENT' '$OPS_PROV' && grep -q 'COST.md' '$OPS_PROV' \
   && grep -q '^## 9. Write .\.env\.example.' '$OPS_PROV'"
check "ops: the app ships COST.md with the spend-cap checklist, and the launch checklists carry all three" \
  "f='$KIT/template/COST.md'; grep -q '^## Spend caps and billing alerts (owner)' \"\$f\" \
   && grep -q 'hard limit' \"\$f\" && grep -q 'Spend cap ON' \"\$f\" && grep -q 'monthly spend limit' \"\$f\" \
   && [ \"\$(grep -c '^- \[ \]' \"\$f\")\" -ge 8 ] \
   && grep -q 'Nightly encrypted backups + a restore drill' '$KIT/docs/PRODUCTION.md' \
   && grep -q 'Spend caps and billing alerts' '$KIT/docs/PRODUCTION.md' \
   && grep -q 'Ops defaults (Better Stack, Cloudflare R2 free tiers)' '$KIT/../../RELEASING.md' \
   && grep -q 'Ops defaults are on' '$KIT/template/docs/runbooks/release.md' \
   && grep -q '## The restore drill' '$KIT/template/docs/runbooks/backup-restore.md'"

# Provision must never put a backup secret or the age PRIVATE key where a transcript
# could see it: no echo/printf/curl of the bucket secret, the DB URL or the uptime
# token, and the key file is only ever passed to `age-keygen` (whose -y prints the
# public half). Setting a GitHub secret with --body "$X" inside the .env prefix is the
# kit's one accepted pattern (step 7) and stays allowed.
_ops_prov_leaks() {  # <skill file>: prints each offending line and fails
  python3 - "$1" <<'PYEOF'
import re, sys
SECRET = r"\$\{?(BACKUP_S3_SECRET_ACCESS_KEY|BACKUP_S3_ACCESS_KEY_ID|SUPABASE_DB_URL|BETTERSTACK_API_TOKEN)\b"
VERB = r"\b(cat|echo|printf|tee|curl|cp|head|tail|less|more|gh secret|gh variable|railway|eas env)\b"
hits = []
for n, line in enumerate(open(sys.argv[1], encoding="utf-8"), 1):
    if re.search(r"\b(echo|printf|curl|tee)\b.*" + SECRET, line):
        hits.append(f"{n}:{line.rstrip()}")
        continue
    # The key file may only ever be an argument to age-keygen (or tested with [ -f ]).
    rest = re.sub(r'age-keygen -[oy] "[^"]*"|\[ -f "[^"]*" \]', "", line)
    if re.search(r"AGE-SECRET-KEY|-backup\.txt|BACKUP_AGE_IDENTITY", rest) and re.search(VERB, rest):
        hits.append(f"{n}:{line.rstrip()}")
if hits:
    print("provision exposes a backup secret or the age private key:\n" + "\n".join(hits))
    sys.exit(1)
PYEOF
}
_ops_prov_plant() {  # <line to append>: the guard must fail on it, naming it
  cp "$OPS_PROV" "$T/prov-ops.md" && printf '%s\n' "$1" >> "$T/prov-ops.md"
  local out; out=$(_ops_prov_leaks "$T/prov-ops.md") && return 1
  printf '%s' "$out" | grep -q 'provision exposes a backup secret or the age private key' && printf '%s' "$out" | grep -qF "$1"
}
check "ops: provision never prints a backup secret, the uptime token or the age private key" "_ops_prov_leaks '$OPS_PROV'"
check "ops provision guard catches: catting the private key file (negative control)" \
  "_ops_prov_plant 'cat \"\$HOME/.config/age/penny-jar-backup.txt\"'"
check "ops provision guard catches: the private key sent to GitHub (negative control)" \
  "_ops_prov_plant 'gh secret set BACKUP_AGE_IDENTITY < \"\$HOME/.config/age/penny-jar-backup.txt\"'"
check "ops provision guard catches: an echoed bucket secret (negative control)" \
  "_ops_prov_plant 'set -a; . ./.env; set +a; echo \"key: \${BACKUP_S3_SECRET_ACCESS_KEY}\"'"

# --- uptime_monitor.py against a local stand-in for Better Stack and Sentry ----------
check "uptime: dry run shows the keyword monitor on /health?deep=1 and redacts the token" \
  "out=\$(BETTERSTACK_API_TOKEN='$OPS_TOKEN' python3 '$OPS_UP' --provider betterstack --api-url https://penny-jar.up.railway.app --name 'Penny Jar API' --dry-run 2>&1) \
   && printf '%s' \"\$out\" | grep -q '\"url\": \"https://penny-jar.up.railway.app/health?deep=1\"' \
   && printf '%s' \"\$out\" | grep -qF '\"required_keyword\": \"\\\"status\\\":\\\"ok\\\"\"' \
   && printf '%s' \"\$out\" | grep -q 'Bearer \*\*\*' && ! printf '%s' \"\$out\" | grep -q '$OPS_TOKEN'"
check "uptime: refuses a missing token (exit 2, named), a plain-http URL, and sentry without --org" \
  "out=\$(env -u BETTERSTACK_API_TOKEN python3 '$OPS_UP' --provider betterstack --api-url https://a.b --name X 2>&1); [ \$? -eq 2 ] \
   && printf '%s' \"\$out\" | grep -q 'BETTERSTACK_API_TOKEN not set' \
   && { python3 '$OPS_UP' --provider betterstack --api-url http://a.b --name X --dry-run >/dev/null 2>&1; [ \$? -eq 2 ]; } \
   && { python3 '$OPS_UP' --provider sentry --api-url https://a.b --name X --dry-run >/dev/null 2>&1; [ \$? -eq 2 ]; }"

_ops_server() {  # starts the stand-in; sets OPS_API and OPS_SRV_PID. Env OPS_EXISTING=1 lists a match.
  cat > "$T/ops_api.py" <<'PYEOF'
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
log, existing = sys.argv[1], sys.argv[2] == "1"
def record(entry):
    with open(log, "a") as f: f.write(json.dumps(entry) + "\n")
class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(obj).encode() if not isinstance(obj, str) else obj.encode())
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        record({"m": "GET", "path": u.path, "q": q, "auth": self.headers["Authorization"]})
        if u.path == "/api/v2/monitors":
            rows = [{"id": "77", "attributes": {"url": q["url"][0]}}] if existing else []
            return self._send(200, {"data": rows})
        return self._send(200, [{"id": "88", "url": q["query"][0]}] if existing else [])
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        record({"m": "POST", "path": self.path, "body": json.loads(body), "auth": self.headers["Authorization"]})
        if "Penny Fail" in body:  # a careless API error that echoes the request headers back
            return self._send(401, "bad token: " + self.headers["Authorization"])
        if self.path == "/api/v2/monitors":
            return self._send(201, {"data": {"id": "1001", "attributes": json.loads(body)}})
        return self._send(201, {"id": "2002"})
    def log_message(self, *a): pass
s = HTTPServer(("127.0.0.1", 0), H)
open(log + ".port", "w").write(str(s.server_address[1]))
s.serve_forever()
PYEOF
  rm -f "$T/ops_api.log" "$T/ops_api.log.port"
  python3 "$T/ops_api.py" "$T/ops_api.log" "${OPS_EXISTING:-0}" & OPS_SRV_PID=$!
  local i; for i in $(seq 50); do [ -s "$T/ops_api.log.port" ] && break; sleep 0.1; done
  OPS_API="http://127.0.0.1:$(cat "$T/ops_api.log.port")"
}
_ops_stop() { kill "$OPS_SRV_PID" 2>/dev/null; wait "$OPS_SRV_PID" 2>/dev/null; }
_ops_up() {  # <expected stdout> <python assertion over the log lines> <uptime_monitor args...>
  local want="$1" assertion="$2" rc=0 out err; shift 2
  out=$(BETTERSTACK_API_TOKEN="$OPS_TOKEN" SENTRY_AUTH_TOKEN="$OPS_TOKEN" python3 "$OPS_UP" --api "$OPS_API" "$@" 2>"$T/ops_up.err") || rc=1
  err=$(cat "$T/ops_up.err")
  [ "$rc" = 0 ] && [ "$out" = "$want" ] || { echo "rc=$rc out=$out err=$err"; rc=1; }
  printf '%s%s' "$out" "$err" | grep -q "$OPS_TOKEN" && { echo "token printed"; rc=1; }
  python3 - "$T/ops_api.log" "$OPS_TOKEN" "$assertion" <<'PYEOF' || rc=1
import json, sys
log = [json.loads(l) for l in open(sys.argv[1])]
assert all(e["auth"] == "Bearer " + sys.argv[2] for e in log), "token not sent as Bearer"
exec(sys.argv[3])
PYEOF
  return $rc
}
_ops_bst_create() {
  _ops_server; local rc=0
  _ops_up "betterstack:1001" '
assert [e["m"] for e in log] == ["GET", "POST"], log
assert log[0]["q"]["url"] == ["https://penny-jar.up.railway.app/health?deep=1"]
b = log[1]["body"]
assert b["monitor_type"] == "keyword" and b["required_keyword"] == "\"status\":\"ok\"", b
assert b["url"] == "https://penny-jar.up.railway.app/health?deep=1" and b["check_frequency"] == 180, b
assert b["pronounceable_name"] == "Penny Jar API" and b["email"] is True, b' \
    --provider betterstack --api-url https://penny-jar.up.railway.app/ --name "Penny Jar API" || rc=1
  _ops_stop; return $rc
}
_ops_bst_reuse() {
  OPS_EXISTING=1 _ops_server; local rc=0
  _ops_up "betterstack:77" 'assert [e["m"] for e in log] == ["GET"], log' \
    --provider betterstack --api-url https://penny-jar.up.railway.app --name "Penny Jar API" || rc=1
  _ops_stop; return $rc
}
_ops_sentry_create() {
  _ops_server; local rc=0
  _ops_up "sentry:2002" '
assert log[0]["path"] == "/api/0/organizations/alex-org/uptime/" and log[0]["q"]["query"] == ["https://penny-jar.up.railway.app/health"], log[0]
assert log[1]["path"] == "/api/0/projects/alex-org/penny-jar-api/uptime/", log[1]
b = log[1]["body"]
assert b["url"] == "https://penny-jar.up.railway.app/health" and b["intervalSeconds"] == 60 and b["timeoutMs"] == 10000, b
assert b["method"] == "GET" and b["environment"] == "production" and b["name"] == "Penny Jar API", b' \
    --provider sentry --api-url https://penny-jar.up.railway.app --name "Penny Jar API" --org alex-org --project penny-jar-api || rc=1
  _ops_stop; return $rc
}
_ops_error_scrubbed() {
  _ops_server; local rc=0 out
  out=$(BETTERSTACK_API_TOKEN="$OPS_TOKEN" python3 "$OPS_UP" --api "$OPS_API" --provider betterstack \
        --api-url https://penny-jar.up.railway.app --name "Penny Fail" 2>&1) && rc=1
  printf '%s' "$out" | grep -q 'betterstack answered 401: bad token: Bearer \*\*\*' || rc=1
  printf '%s' "$out" | grep -q "$OPS_TOKEN" && rc=1
  _ops_stop; return $rc
}
check "uptime: Better Stack keyword monitor created on /health?deep=1; stdout is only provider:id" "_ops_bst_create"
check "uptime: a monitor already on that URL is reused, not duplicated" "_ops_bst_reuse"
check "uptime: Sentry Uptime monitor created on the project, every minute, production" "_ops_sentry_create"
check "uptime: an API error that echoes the token back is shown scrubbed" "_ops_error_scrubbed"

# --- the app's backup guard (tests/test_backup.py), pristine and planted ------------
_ops_plant() {  # <edit function> <expected message>: the app's backup test must fail on it
  local c="$T/ops-plant" out; rm -rf "$c"; mkdir -p "$c"
  cp -R "$APP/tests" "$APP/scripts" "$APP/.github" "$APP/pyproject.toml" "$c/" || return 1
  (cd "$c" && "$1") || return 1
  out=$(cd "$c" && "$OPS_PY" -m pytest -q -p no:cacheprovider tests/test_backup.py 2>&1) && return 1
  printf '%s' "$out" | grep -qF -- "$2"
}
_ops_echo_url() { sed -i 's|^stamp=|echo "db: $SUPABASE_DB_URL" >\&2\nstamp=|' scripts/backup-db.sh && grep -q 'echo "db: \$SUPABASE_DB_URL"' scripts/backup-db.sh; }
_ops_env_dump() { sed -i 's|^stamp=|env >\&2\nstamp=|' scripts/backup-db.sh && grep -qx 'env >&2' scripts/backup-db.sh; }
_ops_xtrace() { sed -i 's|^{ set +x; } 2>/dev/null$|set -x|' scripts/backup-db.sh && grep -qx 'set -x' scripts/backup-db.sh; }
_ops_identity() { sed -i 's|^          BACKUP_AGE_RECIPIENT:|          AGE_IDENTITY: ${{ secrets.BACKUP_AGE_IDENTITY }}\n          BACKUP_AGE_RECIPIENT:|' .github/workflows/backup.yml && grep -q AGE_IDENTITY .github/workflows/backup.yml; }
_ops_no_age() { sed -i 's|run_quiet "encrypting" .*|cp "$work/backup.tgz" "$work/$name"|' scripts/backup-db.sh && ! grep -q 'run_quiet "encrypting"' scripts/backup-db.sh; }
if [ -x "$OPS_PY" ]; then
  check "backup: the rendered app's backup + uptime-keyword tests pass" \
    "cd '$APP' && '$OPS_PY' -m pytest -q -p no:cacheprovider tests/test_backup.py tests/test_health.py tests/harness/test_workflow_lint.py"
  check "backup guard catches: the script echoing the database URL (negative control)" \
    "_ops_plant _ops_echo_url 'backup-db.sh:'"
  check "backup guard catches: an env dump the static lint can't see, by running it (negative control)" \
    "_ops_plant _ops_env_dump 'the backup printed a secret'"
  check "backup guard catches: xtrace turned on (negative control)" \
    "_ops_plant _ops_xtrace 'turns on xtrace'"
  check "backup guard catches: a decryption key handed to the workflow (negative control)" \
    "_ops_plant _ops_identity 'references a decryption key'"
  check "backup guard catches: uploading the tarball without age (negative control)" \
    "_ops_plant _ops_no_age \"doesn't encrypt with age\""
else
  skip "backup: the app's backup guard and its negative controls (needs the rendered app's venv)" "venv"
fi

# --- the real round trip: Postgres -> supabase db dump -> age -> bucket -> restore ----
# `supabase db dump` runs pg_dump in Docker; a shim with the same flags runs pg_dump
# directly, so this needs only Postgres, pg_dump and age. The age key is generated here,
# in $T, outside the app: restore-drill.sh refuses a key file inside the repo.
if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ] && command -v age >/dev/null 2>&1 && command -v pg_dump >/dev/null 2>&1; then
  OPS_BASE="${APPBOX_SELFTEST_DATABASE_URL%/*}"
  OPS_SRC="appbox_ops_src_$$" OPS_DST="appbox_ops_dst_$$"
  OPS_BIN="$T/ops-bin"; mkdir -p "$OPS_BIN" "$T/ops-s3"
  cat > "$OPS_BIN/supabase" <<'SH'
#!/usr/bin/env bash
# supabase db dump --db-url URL -f FILE [--role-only | --use-copy --data-only]
out="" kind=schema url=""
while [ $# -gt 0 ]; do case "$1" in -f) out="$2"; shift 2 ;; --db-url) url="$2"; shift 2 ;;
  --role-only) kind=roles; shift ;; --data-only) kind=data; shift ;; *) shift ;; esac; done
db="${url##*/}"   # the planted password in the URL is never used: connect as the selftest does
case "$kind" in
  roles) echo "-- no custom roles" > "$out" ;;
  # Like the real CLI, which rewrites schema creation so a restore into a fresh project works.
  schema) pg_dump "$OPS_SHIM_BASE/$db" --schema-only --no-owner --no-privileges -n public \
            | sed -E 's/^CREATE SCHEMA ([a-z"]+);/CREATE SCHEMA IF NOT EXISTS \1;/' > "$out" ;;
  data) pg_dump "$OPS_SHIM_BASE/$db" --data-only --no-owner -n public -n auth -f "$out" ;;
esac
SH
  cat > "$OPS_BIN/aws" <<'SH'
#!/usr/bin/env bash
# aws s3 cp SRC DEST [...]: one side is s3://bucket/key, mapped into $OPS_FAKE_S3
echo "$*" >> "$OPS_FAKE_S3/argv.log"
src="$3" dst="$4"
case "$src" in s3://*) src="$OPS_FAKE_S3/${src#s3://}" ;; esac
case "$dst" in s3://*) dst="$OPS_FAKE_S3/${dst#s3://}"; mkdir -p "$(dirname "$dst")" ;; esac
cp "$src" "$dst"
SH
  chmod +x "$OPS_BIN/supabase" "$OPS_BIN/aws"
  _ops_db() { psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -v ON_ERROR_STOP=1 -c "$1"; }
  _ops_prepare() {  # <db> [migrate]: a fresh database with the platform stubs (+ the app's migrations)
    _ops_db "drop database if exists $1 with (force)" && _ops_db "create database $1" || return 1
    psql "$OPS_BASE/$1" -X -q -v ON_ERROR_STOP=1 -f "$APP/supabase/ci/platform_stubs.sql" >/dev/null || return 1
    [ "${2:-}" = migrate ] || return 0
    local m; for m in "$APP"/supabase/migrations/*.sql; do
      psql "$OPS_BASE/$1" -X -q -v ON_ERROR_STOP=1 -f "$m" >/dev/null || return 1
    done
    psql "$OPS_BASE/$1" -X -q -v ON_ERROR_STOP=1 -c \
      "insert into auth.users (id, email) values ('00000000-0000-4000-8000-00000000c0de', 'saver@pennyjar.app'), ('00000000-0000-4000-8000-00000000beef', 'other@pennyjar.app')" >/dev/null
  }
  age-keygen -o "$T/ops-backup-key.txt" 2>/dev/null
  OPS_RECIPIENT="$(age-keygen -y "$T/ops-backup-key.txt")"
  age-keygen -o "$T/ops-other-key.txt" 2>/dev/null
  _ops_backup() {  # [extra env...]: runs the app's backup-db.sh against the source db with planted secrets
    env PATH="$OPS_BIN:$PATH" OPS_SHIM_BASE="$OPS_BASE" OPS_FAKE_S3="$T/ops-s3" \
      SUPABASE_DB_URL="postgresql://postgres.abcdefghij:$OPS_DB_PW@localhost:5432/$OPS_SRC" \
      BACKUP_AGE_RECIPIENT="$OPS_RECIPIENT" BACKUP_S3_BUCKET=penny-backups \
      BACKUP_S3_ENDPOINT=https://acct.r2.cloudflarestorage.com \
      AWS_ACCESS_KEY_ID=planted-id AWS_SECRET_ACCESS_KEY="$OPS_S3_KEY" "$@" \
      bash "$APP/scripts/backup-db.sh"
  }
  _ops_no_secret() {  # <text>: none of the planted secrets, nor the age private key
    local priv; priv=$(grep '^AGE-SECRET-KEY' "$T/ops-backup-key.txt")
    printf '%s' "$1" | grep -qF -e "$OPS_DB_PW" -e "$OPS_S3_KEY" -e "$priv" && { echo "a secret was printed"; return 1; }
    return 0
  }
  _ops_round_trip() {
    local rc=0 out obj
    _ops_prepare "$OPS_SRC" migrate || return 1
    rm -rf "$T/ops-s3"/*; mkdir -p "$T/ops-s3"
    out=$(_ops_backup 2>&1) || { echo "backup failed: $out"; rc=1; }
    _ops_no_secret "$out" || rc=1
    _ops_no_secret "$(cat "$T/ops-s3/argv.log")" || rc=1
    obj=$(ls "$T"/ops-s3/penny-backups/db/db-*.tar.age 2>/dev/null | head -1)
    [ -n "$obj" ] || { echo "nothing uploaded: $out"; return 1; }
    [ "$(head -c 21 "$obj")" = "age-encryption.org/v1" ] || { echo "not age output"; rc=1; }
    grep -qa 'saver@pennyjar.app' "$obj" && { echo "plaintext in the uploaded object"; rc=1; }
    printf '%s' "$out" | grep -q "uploaded s3://penny-backups/db/$(basename "$obj")" || rc=1
    # The drill, from the bucket, into an empty database: every table back, rows intact.
    _ops_prepare "$OPS_DST" || return 1
    out=$(env PATH="$OPS_BIN:$PATH" OPS_FAKE_S3="$T/ops-s3" BACKUP_AGE_IDENTITY_FILE="$T/ops-backup-key.txt" \
          bash "$APP/scripts/restore-drill.sh" "s3://penny-backups/db/$(basename "$obj")" --target "$OPS_BASE/$OPS_DST" 2>&1) \
      || { echo "drill failed: $out"; rc=1; }
    printf '%s\n' "$out" | grep -qx '  profiles 2' || { echo "profiles not restored: $out"; rc=1; }
    printf '%s\n' "$out" | grep -qx '  keep_alive 1' || rc=1
    printf '%s' "$out" | grep -q 'restore-drill: passed (' || rc=1
    [ "$(psql "$OPS_BASE/$OPS_DST" -X -tAc "select count(*) from auth.users where email = 'saver@pennyjar.app'")" = 1 ] || rc=1
    _ops_no_secret "$out" || rc=1
    return $rc
  }
  check "backup round trip: real Postgres dump, age-encrypted upload, restore drill brings every row back, no secret printed" "_ops_round_trip"
  # Negative controls on the same databases.
  check "restore drill refuses: a target that already has tables (it would restore over production)" \
    "out=\$(BACKUP_AGE_IDENTITY_FILE='$T/ops-backup-key.txt' bash '$APP/scripts/restore-drill.sh' \"\$(ls '$T'/ops-s3/penny-backups/db/db-*.tar.age | head -1)\" --target '$OPS_BASE/$OPS_SRC' 2>&1); [ \$? -eq 2 ] \
     && printf '%s' \"\$out\" | grep -q 'the target already has .* table(s) in public'"
  check "restore drill refuses: the wrong key, and a key file inside the repo" \
    "f=\$(ls '$T'/ops-s3/penny-backups/db/db-*.tar.age | head -1); _ops_prepare $OPS_DST \
     && out=\$(BACKUP_AGE_IDENTITY_FILE='$T/ops-other-key.txt' bash '$APP/scripts/restore-drill.sh' \"\$f\" --target '$OPS_BASE/$OPS_DST' 2>&1); [ \$? -eq 1 ] \
     && printf '%s' \"\$out\" | grep -q \"couldn't decrypt\" \
     && cp '$T/ops-backup-key.txt' '$APP/.ops-key.txt' \
     && out=\$(BACKUP_AGE_IDENTITY_FILE='$APP/.ops-key.txt' bash '$APP/scripts/restore-drill.sh' \"\$f\" --target '$OPS_BASE/$OPS_DST' 2>&1); rc=\$?; rm -f '$APP/.ops-key.txt'; [ \$rc -eq 2 ] \
     && printf '%s' \"\$out\" | grep -q 'the private key file is inside the repo'"
  cat > "$OPS_BIN/fake-age" <<'SH'
#!/usr/bin/env bash
# an "age" that writes the plaintext through: -r R... -o OUT IN
while [ $# -gt 1 ]; do [ "$1" = -o ] && { out="$2"; shift; }; shift; done
cp "$1" "$out"
SH
  chmod +x "$OPS_BIN/fake-age"
  _ops_plaintext_refused() {
    local out rc=0
    rm -rf "$T/ops-s3"/*
    out=$(_ops_backup AGE="$OPS_BIN/fake-age" 2>&1) && return 1
    printf '%s' "$out" | grep -q "isn't age output; refusing to upload" || rc=1
    [ ! -e "$T/ops-s3/penny-backups" ] || rc=1
    _ops_no_secret "$out" || rc=1
    return $rc
  }
  check "backup refuses: an 'age' that writes plaintext never reaches the bucket (negative control)" "_ops_plaintext_refused"
  _ops_db "drop database if exists $OPS_SRC with (force)" >/dev/null 2>&1
  _ops_db "drop database if exists $OPS_DST with (force)" >/dev/null 2>&1
else
  skip "backup round trip + restore drill on a real Postgres" "APPBOX_SELFTEST_DATABASE_URL, pg_dump and age"
fi
