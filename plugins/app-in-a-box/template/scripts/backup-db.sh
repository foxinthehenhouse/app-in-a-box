#!/usr/bin/env bash
# Nightly database backup: dump, encrypt, upload. Run by .github/workflows/backup.yml;
# runs anywhere with the same environment. The restore side is scripts/restore-drill.sh
# and docs/runbooks/backup-restore.md.
#
#   scripts/backup-db.sh               # dump + encrypt + upload to the bucket
#   scripts/backup-db.sh --out <dir>   # dump + encrypt into <dir>, upload nothing
#
# Environment. Secrets come from the environment only, never from arguments, and this
# script never prints one:
#   SUPABASE_DB_URL         Session pooler connection string (SECRET: holds the DB password)
#   BACKUP_AGE_RECIPIENT    age PUBLIC key(s) to encrypt to, space-separated (age1...)
#   BACKUP_S3_BUCKET        bucket name (not needed with --out)
#   BACKUP_S3_ENDPOINT      S3-compatible endpoint, e.g. https://<account>.r2.cloudflarestorage.com
#                           (leave blank for AWS S3)
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
#                           the bucket's credentials (SECRET), read by the aws CLI itself
#
# What's dumped is what Supabase's backup guide restores: roles, schema, and data (as
# COPY), each with `supabase db dump`. The three files are tarred and encrypted with age
# to the PUBLIC key, so this machine (and GitHub) can write a backup but never read one:
# the private key stays with the owner. The plaintext lives only in a private temp dir
# that's removed on exit. Errors from the CLIs are shown with every secret replaced by
# ***, and the script refuses xtrace, which would print each command with its values.
#
# SUPABASE=<command>, AGE=<command>, AWS=<command> override the CLIs (tests use this).
set -euo pipefail
{ set +x; } 2>/dev/null

out_dir=""
case "${1:-}" in
  "") ;;
  --out) out_dir="${2:?--out needs a directory}" ;;
  -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
  *) echo "backup-db: unknown option $1 (see --help)" >&2; exit 2 ;;
esac

read -r -a supabase <<<"${SUPABASE:-supabase}"
read -r -a age_cli <<<"${AGE:-age}"
read -r -a aws <<<"${AWS:-aws}"

# Every value that must never reach the log, including the password inside the URL.
db_pw="${SUPABASE_DB_URL:-}"; db_pw="${db_pw#*://}"; db_pw="${db_pw%%@*}"; db_pw="${db_pw#*:}"
_secrets=("${SUPABASE_DB_URL:-}" "$db_pw" "${AWS_SECRET_ACCESS_KEY:-}" "${AWS_ACCESS_KEY_ID:-}")
scrub() {  # stdin -> stdout, each secret replaced by ***
  local text s
  text="$(cat)"
  for s in "${_secrets[@]}"; do
    [ "${#s}" -ge 4 ] && text="${text//"$s"/***}"
  done
  printf '%s\n' "$text"
}
fail() { echo "backup-db: $*" >&2; exit 1; }
run_quiet() {  # <label> <cmd...>: runs it; on failure shows its output, scrubbed
  local label="$1" log; shift
  log="$work/.log"
  if ! "$@" >"$log" 2>&1; then
    echo "backup-db: $label failed:" >&2
    tail -n 30 "$log" | scrub >&2
    exit 1
  fi
}

missing=()
[ -n "${SUPABASE_DB_URL:-}" ] || missing+=(SUPABASE_DB_URL)
[ -n "${BACKUP_AGE_RECIPIENT:-}" ] || missing+=(BACKUP_AGE_RECIPIENT)
if [ -z "$out_dir" ]; then
  [ -n "${BACKUP_S3_BUCKET:-}" ] || missing+=(BACKUP_S3_BUCKET)
  [ -n "${AWS_ACCESS_KEY_ID:-}" ] || missing+=(AWS_ACCESS_KEY_ID)
  [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] || missing+=(AWS_SECRET_ACCESS_KEY)
fi
if [ "${#missing[@]}" -gt 0 ]; then
  echo "backup-db: not set: ${missing[*]} (see docs/runbooks/backup-restore.md)" >&2
  exit 2
fi

recipients=() keys=0
for r in $BACKUP_AGE_RECIPIENT; do
  case "$r" in
    AGE-SECRET-KEY-*)
      # Never echo it back: name the variable, not the value.
      echo "backup-db: BACKUP_AGE_RECIPIENT holds an age PRIVATE key. It must be the public key (age1...); revoke that private key and make a new pair." >&2
      exit 2 ;;
    age1*) recipients+=(-r "$r"); keys=$((keys + 1)) ;;
    *) echo "backup-db: BACKUP_AGE_RECIPIENT has an entry that isn't an age public key (age1...)" >&2; exit 2 ;;
  esac
done

work="$(mktemp -d)"
chmod 700 "$work"
trap 'rm -rf "$work"' EXIT

stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
name="db-$stamp.tar.age"

run_quiet "dumping roles" "${supabase[@]}" db dump --db-url "$SUPABASE_DB_URL" -f "$work/roles.sql" --role-only
run_quiet "dumping the schema" "${supabase[@]}" db dump --db-url "$SUPABASE_DB_URL" -f "$work/schema.sql"
run_quiet "dumping the data" "${supabase[@]}" db dump --db-url "$SUPABASE_DB_URL" -f "$work/data.sql" --use-copy --data-only

for f in roles schema data; do
  [ -f "$work/$f.sql" ] || fail "supabase db dump wrote no $f.sql"
done
# An empty schema means the URL points at the wrong database: a backup of nothing
# would read as a green run every night until the day it's needed.
grep -qi 'create table' "$work/schema.sql" || fail "schema.sql has no CREATE TABLE: is SUPABASE_DB_URL the app's database?"

tar -C "$work" -czf "$work/backup.tgz" roles.sql schema.sql data.sql
run_quiet "encrypting" "${age_cli[@]}" "${recipients[@]}" -o "$work/$name" "$work/backup.tgz"
rm -f "$work/roles.sql" "$work/schema.sql" "$work/data.sql" "$work/backup.tgz"
[ "$(head -c 21 "$work/$name")" = "age-encryption.org/v1" ] || fail "the encrypted file isn't age output; refusing to upload it"
size=$(wc -c <"$work/$name" | tr -d ' ')

if [ -n "$out_dir" ]; then
  mkdir -p "$out_dir"
  mv "$work/$name" "$out_dir/$name"
  echo "backup-db: wrote $out_dir/$name ($size bytes, encrypted to $keys key(s))"
  exit 0
fi

key="db/$name"
endpoint=()
[ -n "${BACKUP_S3_ENDPOINT:-}" ] && endpoint=(--endpoint-url "$BACKUP_S3_ENDPOINT")
run_quiet "uploading" "${aws[@]}" s3 cp "$work/$name" "s3://$BACKUP_S3_BUCKET/$key" ${endpoint[@]+"${endpoint[@]}"} --only-show-errors
echo "backup-db: uploaded s3://$BACKUP_S3_BUCKET/$key ($size bytes, age-encrypted)"
