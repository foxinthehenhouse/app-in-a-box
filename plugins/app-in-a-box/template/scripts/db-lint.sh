#!/usr/bin/env bash
# Migration linter: squawk (https://squawkhq.com) on every supabase/migrations/*.sql,
# with the rules in .squawk.toml. It catches what applying to an EMPTY database can't:
# statements that lock or break a database that already has rows and a deployed app
# reading it (an index built without CONCURRENTLY, a NOT NULL column with no default, a
# renamed or dropped column). Run by .github/workflows/db.yml; no database needed.
#
#   scripts/db-lint.sh
#
# Uses `squawk` from PATH when it is the pinned version, otherwise runs the pinned npm
# package through npx (npm checks the package's integrity hash from the registry).
#
# Then a NEGATIVE CONTROL: three planted migrations (one per rule above) must each fail
# with their rule's name, or the linter is blind and this fails.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SQUAWK_VERSION="2.67.0"

if command -v squawk >/dev/null 2>&1 && [ "$(squawk --version 2>/dev/null)" = "squawk $SQUAWK_VERSION" ]; then
  SQUAWK=(squawk)
elif command -v npx >/dev/null 2>&1; then
  SQUAWK=(npx --yes "squawk-cli@$SQUAWK_VERSION")
else
  echo "db-lint: needs squawk $SQUAWK_VERSION on PATH, or Node's npx to fetch it" >&2
  exit 2
fi
SQUAWK+=(--config .squawk.toml)

files=()  # no mapfile: macOS still ships bash 3.2
while IFS= read -r f; do files+=("$f"); done < <(find supabase/migrations -maxdepth 1 -name '*.sql' | LC_ALL=C sort)
[ "${#files[@]}" -gt 0 ] || { echo "db-lint: no migrations found" >&2; exit 1; }
fail=0

echo "== squawk on ${#files[@]} migrations"
if "${SQUAWK[@]}" "${files[@]}"; then
  echo "squawk: no unsafe statements"
else
  echo "::error::squawk found statements that are unsafe on a live database (above)."
  echo "See .agents/rules/db-migrations.md (expand, then contract) for the safe shape."
  fail=1
fi

echo "== negative control (planted unsafe migrations must be caught)"
TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT
printf 'create index profiles_onboarded_idx on public.profiles (onboarded);\n' \
  > "$TMPD/index.sql"
printf 'alter table public.profiles add column plan text not null;\n' > "$TMPD/required.sql"
printf 'alter table public.profiles rename column display_name to name;\n' > "$TMPD/rename.sql"
for plant in index:require-concurrent-index-creation required:adding-required-field rename:renaming-column; do
  f="$TMPD/${plant%%:*}.sql"; rule="${plant#*:}"
  if out="$("${SQUAWK[@]}" --reporter gcc "$f" 2>&1)"; then
    echo "::error::squawk passed a planted ${plant%%:*} migration; the linter is blind"; fail=1
  elif grep -q -- "$rule" <<<"$out"; then
    echo "caught: $rule"
  else
    printf '%s\n' "$out"
    echo "::error::squawk failed the planted ${plant%%:*} migration, but not on $rule"; fail=1
  fi
done

if [ "$fail" -eq 0 ]; then echo "db-lint: all green"; else echo "db-lint: FAILED"; fi
exit "$fail"
