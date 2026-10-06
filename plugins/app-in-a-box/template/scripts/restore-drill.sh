#!/usr/bin/env bash
# Restore drill: prove a backup from scripts/backup-db.sh actually restores.
# A backup nobody has restored is a hope, not a backup. Run this monthly and before
# launch; docs/runbooks/backup-restore.md has the whole drill and its log.
#
#   BACKUP_AGE_IDENTITY_FILE=~/.config/age/<app>-backup.txt \
#     scripts/restore-drill.sh <db-....tar.age | s3://bucket/db/db-....tar.age> --target <EMPTY database URL>
#
# The target must be an EMPTY database with Supabase's platform schemas: a scratch
# Supabase project, or a local stack started from an empty folder (`supabase init` +
# `supabase start` in a temp dir, NOT this repo, whose stack already has your
# migrations). The drill refuses a target that already has tables in `public`, which
# is also what stops it from ever restoring over production.
#
# Steps: fetch (an s3:// path goes through the aws CLI with BACKUP_S3_ENDPOINT, like the
# backup), decrypt with the private key file, restore roles + schema + data in ONE
# transaction (ON_ERROR_STOP), then count the rows in every public table. Any error
# fails the drill. The key is read from a FILE outside the repo and never printed.
#
# AGE=<command>, AWS=<command> override the CLIs (tests use this).
set -euo pipefail
{ set +x; } 2>/dev/null
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

src="" target=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target) target="${2:?--target needs a database URL}"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "restore-drill: unknown option $1 (see --help)" >&2; exit 2 ;;
    *) src="$1"; shift ;;
  esac
done
[ -n "$src" ] && [ -n "$target" ] || { echo "usage: scripts/restore-drill.sh <backup> --target <empty database URL>" >&2; exit 2; }

identity="${BACKUP_AGE_IDENTITY_FILE:-}"
[ -n "$identity" ] && [ -f "$identity" ] || {
  echo "restore-drill: set BACKUP_AGE_IDENTITY_FILE to the path of the backup's private key file" >&2; exit 2; }
# The private key lives outside the repo (a password manager, ~/.config/age). Inside it,
# one `git add -A` would publish every backup's contents.
case "$(cd "$(dirname "$identity")" && pwd)/" in
  "$ROOT"/*) echo "restore-drill: the private key file is inside the repo. Move it out (and never commit it)." >&2; exit 2 ;;
esac

read -r -a age_cli <<<"${AGE:-age}"
read -r -a aws <<<"${AWS:-aws}"
PSQL=(psql "$target" -X -q -v ON_ERROR_STOP=1)

tables=$("${PSQL[@]}" -tAc "select count(*) from information_schema.tables where table_schema = 'public'") || {
  echo "restore-drill: can't connect to the target database" >&2; exit 1; }
if [ "$tables" != "0" ]; then
  echo "restore-drill: the target already has $tables table(s) in public. A drill restores into an EMPTY database (and never into production)." >&2
  exit 2
fi

work="$(mktemp -d)"
chmod 700 "$work"
trap 'rm -rf "$work"' EXIT

case "$src" in
  s3://*)
    endpoint=()
    [ -n "${BACKUP_S3_ENDPOINT:-}" ] && endpoint=(--endpoint-url "$BACKUP_S3_ENDPOINT")
    "${aws[@]}" s3 cp "$src" "$work/backup.tar.age" ${endpoint[@]+"${endpoint[@]}"} --only-show-errors
    file="$work/backup.tar.age" ;;
  *) file="$src" ;;
esac
[ -f "$file" ] || { echo "restore-drill: no backup at $src" >&2; exit 2; }

"${age_cli[@]}" -d -i "$identity" -o "$work/backup.tgz" "$file" || {
  echo "restore-drill: couldn't decrypt $src with that key (is it this app's backup key?)" >&2; exit 1; }
tar -C "$work" -xzf "$work/backup.tgz" roles.sql schema.sql data.sql

started=$(date +%s)
"${PSQL[@]}" --single-transaction \
  -f "$work/roles.sql" \
  -f "$work/schema.sql" \
  -c 'set session_replication_role = replica' \
  -f "$work/data.sql" >/dev/null

echo "restore-drill: restored $(basename "$src") in $(( $(date +%s) - started ))s. Rows per public table:"
counts=$("${PSQL[@]}" -tA -F ' ' <<'SQL'
select format('select %L, count(*) from public.%I', table_name, table_name)
from information_schema.tables
where table_schema = 'public' and table_type = 'BASE TABLE'
order by table_name
\gexec
SQL
)
printf '%s\n' "$counts" | sed 's/^/  /'
restored=$(printf '%s\n' "$counts" | grep -c . || true)
[ "$restored" -gt 0 ] || { echo "restore-drill: FAILED: no tables came back" >&2; exit 1; }
echo "restore-drill: passed ($restored tables). Log it in docs/runbooks/backup-restore.md."
