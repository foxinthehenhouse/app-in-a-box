# recipe-search: sourced by selftest.sh with $KIT, $APP (rendered app), $T and the
# check/refuses/skip helpers. The recipe ships files, not prose alone, so this area
# APPLIES it to a copy of the rendered app the way the skill tells an agent to, then
# runs that app's own guards over the result:
#   - static: the skill's shape, and the SQL's load-bearing clauses (invoker, pinned
#     search_path, API grants, websearch_to_tsquery, keyset cursor, GIN, HNSW, RRF)
#   - backend: the app's whole pytest suite + ruff green with the recipe in; and the
#     search tests, the wire contract and the migration guards each FAIL on a plant
#   - database (APPBOX_SELFTEST_DATABASE_URL): the app's DB gate green with the recipe
#     in, and the pgTAP isolation tests FAIL against a planted SECURITY DEFINER
#     search_items() with no user filter (the shipped negative control) and against
#     the same rewrite of the hybrid function. Runs in a database of its own.
#   - mobile: applied too, then the app's node-only guards (analytics coverage, Maestro
#     coverage, strings, test presence, design tells), with plants. tsc, eslint and jest
#     need a real Expo app with node_modules, which this area doesn't build.
RS="$KIT/skills/recipe-search"
RS_APP="$T/rs-app"
RS_PY="$APP/.venv/bin/python"

_rs_skill_shape() {
  local f="$RS/SKILL.md" p
  head -1 "$f" | grep -qx -- '---' && grep -q '^name: recipe-search$' "$f" \
    && grep -q '^description: .*full-text' "$f" || { echo "frontmatter"; return 1; }
  for p in '^## Steps' '^## Env / wiring checklist' '^## Tests to add' '^## Done means' '^## When to add a search engine'; do
    grep -q "$p" "$f" || { echo "missing section: $p"; return 1; }
  done
  # Every file the skill tells you to copy exists, and every shipped file is mentioned.
  for p in $(grep -o '`\(sql\|files\|snippets\)/[^`]*`' "$f" | tr -d '`' | sort -u); do
    [ -e "$RS/$p" ] || { echo "SKILL.md names a missing file: $p"; return 1; }
  done
  (cd "$RS" && find sql files snippets -type f -not -path '*/__pycache__/*' -not -path '*/.ruff_cache/*') | while read -r p; do
    grep -qF "$p" "$f" || { echo "shipped but never mentioned in SKILL.md: $p"; exit 1; }
  done
}
check "recipe-search: skill shape (frontmatter, sections, every shipped file named and present)" _rs_skill_shape

# The SQL clauses that make it safe and fast. Each is one regex over the shipped file.
_rs_sql_has() {  # <file> <regex>...
  local f="$RS/sql/$1" body; shift
  body="$(sed 's/--.*$//' "$f" | tr -s '[:space:]' ' ' | tr '[:upper:]' '[:lower:]')"
  for re in "$@"; do grep -qE -- "$re" <<<"$body" || { echo "$f: no match for: $re"; return 1; }; done
}
check "recipe-search: FTS migration: weighted generated tsvector, GIN, invoker RPC with pinned search_path, keyset, websearch, API grants" \
  "_rs_sql_has search.sql \
    'search_tsv tsvector generated always as \( setweight\(to_tsvector\(.simple., coalesce\(title' \
    \"setweight\(to_tsvector\('simple', coalesce\(body, ''\)\), 'b'\)\" \
    'create index if not exists items_search_idx on public.items using gin \(search_tsv\)' \
    'security invoker set search_path = .. as' \
    'where i.user_id = \(select auth.uid\(\)\)' \
    'websearch_to_tsquery' \
    '< p_after_rank or \(ts_rank_cd\(i.search_tsv, q.tsq\)::real = p_after_rank and i.id > p_after_id\)' \
    'order by rank desc, i.id' \
    'revoke execute on function public.search_items\(text, integer, real, uuid\) from public, anon' \
    'grant execute on function public.search_items\(text, integer, real, uuid\) to authenticated'"
check "recipe-search: hybrid migration: pgvector in extensions, HNSW cosine, invoker RRF over both lists" \
  "_rs_sql_has search_hybrid.sql \
    'create extension if not exists vector with schema extensions' \
    'using hnsw \(embedding extensions.vector_cosine_ops\)' \
    'security invoker set search_path = .. as' \
    '1.0 / \(greatest\(coalesce\(p_rrf_k, 60\), 1\) \+ fts.pos\)' \
    'from fts full join vec on fts.id = vec.id' \
    'revoke execute on function public.search_items_hybrid\(.*\) from public, anon'"
check "recipe-search: the negative control is the definer-without-filter rewrite (so the pgTAP check below means what it says)" \
  "_rs_sql_has negative_control.sql 'security definer' && ! grep -q 'auth.uid' '$RS/sql/negative_control.sql'"
check "recipe-search: skips external engines, with the when-to-add note (no pg_search: not on Supabase)" \
  "grep -q 'Typesense' '$RS/SKILL.md' && grep -q 'Meilisearch' '$RS/SKILL.md' && grep -q 'pg_search' '$RS/SKILL.md'"

# ---- apply the recipe to a copy of the rendered app --------------------------------------
_rs_apply() {  # <app dir>: what SKILL.md's steps do, mechanically
  local a="$1"
  cp "$RS/sql/search.sql" "$a/supabase/migrations/20991231000000_search.sql"
  cp "$RS/sql/search.test.sql" "$a/supabase/tests/database/search.test.sql"
  cat "$RS/sql/negative_control.sql" >> "$a/supabase/ci/negative_control.sql"
  (cd "$RS/files" && tar -cf - .) | (cd "$a" && tar -xf -)
  cat "$RS/snippets/api.ts" >> "$a/mobile/lib/api.ts"
  python3 - "$a" "$RS" <<'PYEOF'
import re, sys
from pathlib import Path
a, rs = Path(sys.argv[1]), Path(sys.argv[2])
def edit(rel, old, new):
    p = a / rel; s = p.read_text()
    assert old in s, f"{rel}: anchor not found: {old!r}"
    p.write_text(s.replace(old, new, 1))
edit("backend/main.py", "import export, internal, me, push  #", "import export, internal, me, push, search  #")
edit("backend/main.py", "    app.include_router(export.router)\n", "    app.include_router(export.router)\n    app.include_router(search.router)\n")
edit("backend/config.py", "    # Register a feature here only when",
     '    "search (Postgres full-text)": ("SUPABASE_URL", "SUPABASE_ANON_KEY"),\n    # Register a feature here only when')
reader = (rs / "snippets/export.py").read_text().split("\n\n\n", 1)[1]
edit("backend/routers/export.py", "# table -> scoped reader.", reader + "\n\n# table -> scoped reader.")
edit("backend/routers/export.py", '    "push_tickets": _read_push_tickets,\n', '    "push_tickets": _read_push_tickets,\n    "items": _read_items,\n')
edit("tests/test_wire_contract.py", "from backend.routers.push import PushTokenIn, PushTokenRef\n",
     "from backend.routers.push import PushTokenIn, PushTokenRef\nfrom backend.routers.search import SearchHit, SearchPage\n")
edit("tests/test_wire_contract.py", '    (DataExport, "DataExportWire"),\n',
     '    (DataExport, "DataExportWire"),\n    (SearchPage, "SearchPageWire"),\n    (SearchHit, "SearchHitWire"),\n')
# The /health "everything wired" tests list every var; search adds one.
edit("tests/test_health.py", '("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SENTRY_DSN")',
     '("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_ANON_KEY", "SENTRY_DSN")')
p = a / "tests/test_prod_hardening.py"
p.write_text(p.read_text().replace('    monkeypatch.setenv("SENTRY_DSN", "x")\n',
     '    monkeypatch.setenv("SENTRY_DSN", "x")\n    monkeypatch.setenv("SUPABASE_ANON_KEY", "x")\n'))
# Mobile: the snippets pasted where SKILL.md step 4 says.
an = "\n".join(l for l in (rs / "snippets/analytics.ts").read_text().splitlines() if not l.startswith("//")).strip("\n")
edit("mobile/lib/analytics.ts", '  errorReferenceCopied: () => capture("error_reference_copied"),\n',
     '  errorReferenceCopied: () => capture("error_reference_copied"),\n' + an + "\n")
en = (rs / "snippets/en.ts").read_text()
edit("mobile/locales/en.ts", '    settings: "Settings",\n  },', '    settings: "Settings",\n    search: "Search",\n  },')
edit("mobile/locales/en.ts", "} as const;", en[en.index("  search: {"):] + "} as const;")
tabs = (rs / "snippets/tabs.tsx").read_text()
native = tabs[tabs.index('      <NativeTabs.Trigger name="search">'):tabs.index("// mobile/app/(app)/_layout.web.tsx")].rstrip() + "\n"
edit("mobile/app/(app)/_layout.tsx", '      <NativeTabs.Trigger name="settings">', native + '      <NativeTabs.Trigger name="settings">')
web = tabs[tabs.index('        <TabTrigger name="search"'):].rstrip() + "\n"
edit("mobile/app/(app)/_layout.web.tsx", '        <TabTrigger name="settings"', web + '        <TabTrigger name="settings"')
demo = (rs / "snippets/demo.ts").read_text()
edit("mobile/lib/demo.ts", "type Handler = ", demo[demo.index("const DEMO_ITEMS"):demo.index("  // inside ROUTES:")].rstrip() + "\n\ntype Handler = ")
edit("mobile/lib/demo.ts", "const ROUTES: Record<string, Handler> = {\n", "const ROUTES: Record<string, Handler> = {\n" + demo[demo.index('  "GET /api/v1/search"'):])
flow = a / "mobile/.maestro/search.yaml"
flow.write_text(flow.read_text().replace("__BUNDLE_ID__", re.search(r"^appId: (.+)$", (a / "mobile/.maestro/home.yaml").read_text(), re.M).group(1)))
edit("AGENTS.md", "| Data export |",
     "| Search | `app/(app)/search.tsx` | `routers/search.py` | `services/search_service.py` | `items` |\n| Data export |")
PYEOF
}
_rs_fresh_copy() {
  rm -rf "$RS_APP" && mkdir -p "$RS_APP" \
    && (cd "$APP" && tar --exclude=node_modules --exclude=.git -cf - .) | (cd "$RS_APP" && tar -xf -) \
    && _rs_apply "$RS_APP"
}
RS_PT="cd '$RS_APP' && '$RS_PY' -m pytest -q -p no:warnings -p no:cacheprovider"
# rs_plant <file> <python edit of s>: edit one file of the applied copy in place.
_rs_plant() { python3 -c "import sys;p=sys.argv[1];s=open(p).read();$2;open(p,'w').write(s)" "$RS_APP/$1"; }

if [ -x "$RS_PY" ] && _rs_fresh_copy; then
  check "recipe-search: applied to a rendered app, its whole pytest suite is green" "$RS_PT"
  check "recipe-search: applied, ruff is clean on the app" "cd '$RS_APP' && '$APP/.venv/bin/ruff' check backend tests"

  cp "$RS_APP/backend/services/search_service.py" "$T/rs-svc.bak"
  _rs_plant backend/services/search_service.py 's=s.replace("f\"Bearer {creds.credentials}\"","f\"Bearer {env(\"SUPABASE_SECRET_KEY\")}\"")'
  refuses "recipe-search: the tests catch a search that runs with the service key instead of the caller's token" \
    "$RS_PT tests/test_search.py" "test_user_db_carries_the_callers_token_not_the_service_key"
  cp "$T/rs-svc.bak" "$RS_APP/backend/services/search_service.py"

  cp "$RS_APP/backend/routers/search.py" "$T/rs-router.bak"
  _rs_plant backend/routers/search.py 's=s.replace("from backend.ratelimit import rate_limit","from backend.db import get_db\nfrom backend.ratelimit import rate_limit").replace("Depends(search_service.get_user_db)","Depends(get_db)")'
  refuses "recipe-search: the tests catch the route searching through the service client (RLS bypassed)" \
    "$RS_PT tests/test_search.py" "test_search_never_uses_the_service_client"
  cp "$T/rs-router.bak" "$RS_APP/backend/routers/search.py"

  cp "$RS_APP/mobile/lib/api.ts" "$T/rs-api.bak"
  _rs_plant mobile/lib/api.ts 's=s.replace("  nextCursor: string | null;\n}\n\nexport interface SearchHit {","}\n\nexport interface SearchHit {")'
  refuses "recipe-search: the wire contract catches the app's SearchPageWire drifting from the API" \
    "$RS_PT tests/test_wire_contract.py" "SearchPage.nextCursor"
  cp "$T/rs-api.bak" "$RS_APP/mobile/lib/api.ts"

  sed -e 's/security invoker/security definer/' "$RS/sql/search.sql" > "$RS_APP/supabase/migrations/20991231000100_planted.sql"
  refuses "recipe-search: the migration guard catches search_items() turned SECURITY DEFINER and left callable by users" \
    "$RS_PT tests/test_prod_migrations.py" "search_items"
  rm -f "$RS_APP/supabase/migrations/20991231000100_planted.sql"
else
  bad "recipe-search: apply the recipe to a copy of the rendered app (needs \$APP's venv from the Backend step)"
fi

# Static checks on the mobile half: the pattern's load-bearing parts are present.
_rs_mobile_shape() {
  local scr="$RS/files/mobile/app/(app)/search.tsx" lib="$RS/files/mobile/lib/search.ts"
  grep -q 'analytics.screenViewed("search")' "$scr" || { echo "screen fires no view event"; return 1; }
  for id in search-screen search-input search-idle search-skeleton search-error search-empty search-results search-more-button; do
    grep -q "testID=\"$id\"" "$scr" || { echo "screen has no $id state"; return 1; }
  done
  grep -q 'useDebouncedValue' "$lib" && grep -q 'SEARCH_DEBOUNCE_MS = 300' "$lib" && grep -q 'useInfiniteQuery' "$lib" \
    || { echo "hook is not debounced + paged"; return 1; }
  grep -q 'analytics.searchPerformed' "$lib" && grep -q 'analytics.searchFailed' "$lib" \
    || { echo "hook misses the success or failure event"; return 1; }
  grep -q 'searchPerformed:' "$RS/snippets/analytics.ts" && grep -q 'searchFailed:' "$RS/snippets/analytics.ts" \
    || { echo "analytics snippet misses a helper"; return 1; }
  grep -q 'id: "search-screen"' "$RS/files/mobile/.maestro/search.yaml" && grep -q '"GET /api/v1/search"' "$RS/snippets/demo.ts" \
    || { echo "no Maestro flow, or no demo handler for it to run against"; return 1; }
  # Every t("search.x") the screen uses is in the strings snippet.
  local k
  for k in $(grep -o 't("search\.[a-zA-Z]*"' "$scr" | sed 's/.*search\.//; s/"//' | sort -u); do
    grep -q "^    $k:" "$RS/snippets/en.ts" || { echo "string search.$k is not in snippets/en.ts"; return 1; }
  done
}
check "recipe-search: mobile pattern: debounced paged hook, every state with a testID, view + performed/failed events, flow + demo handler, strings" _rs_mobile_shape
# The app's node-only mobile guards (they run without node_modules) over the applied
# copy; tsc, eslint and jest need a real Expo app (the --mobile run).
if command -v node >/dev/null 2>&1 && [ -d "$RS_APP/mobile" ]; then
  RS_MG="cd '$RS_APP/mobile' && node scripts/check-analytics-coverage.js && node scripts/check-maestro-coverage.js \
    && node scripts/check-hardcoded-strings.js && node scripts/check-test-presence.js && node scripts/check-design-tells.js"
  check "recipe-search: applied, the app's mobile guards pass (analytics, Maestro coverage, strings, test presence, design tells)" "$RS_MG"
  cp "$RS_APP/mobile/lib/search.ts" "$T/rs-search-ts.bak"
  _rs_plant mobile/lib/search.ts 's=s.replace("analytics.searchFailed(","void (")'
  refuses "recipe-search: the analytics guard catches the failure event losing its call site" \
    "cd '$RS_APP/mobile' && node scripts/check-analytics-coverage.js" "searchFailed"
  cp "$T/rs-search-ts.bak" "$RS_APP/mobile/lib/search.ts"
  _rs_plant mobile/.maestro/search.yaml 's=s.replace("id: \"search-screen\"","id: \"home-screen\"")'
  refuses "recipe-search: the Maestro guard catches the search screen with no flow asserting on it" \
    "cd '$RS_APP/mobile' && node scripts/check-maestro-coverage.js" "search"
  cp "$RS/files/mobile/.maestro/search.yaml" "$RS_APP/mobile/.maestro/search.yaml"
else
  skip "recipe-search: the app's mobile guards over the applied copy" "node"
fi

check "recipe-search: the search events carry lengths and counts, never the query text" \
  "grep -q 'query_length: q.length' '$RS/files/mobile/lib/search.ts' && ! grep -qE '(^|[ {,])(q|query|text):' '$RS/snippets/analytics.ts'"

# ---- real Postgres -------------------------------------------------------------------------
if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ]; then
  RS_DB="appbox_rs_$$"
  RS_URL="$(python3 -c "import sys,urllib.parse as u;p=u.urlsplit(sys.argv[1]);print(u.urlunsplit(p._replace(path='/$RS_DB')))" "$APPBOX_SELFTEST_DATABASE_URL")"
  psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "drop database if exists $RS_DB" -c "create database $RS_DB" >/dev/null 2>&1 \
    || bad "recipe-search: create a scratch database next to APPBOX_SELFTEST_DATABASE_URL (needs a superuser URL)"
  RS_VECTOR="$(psql "$RS_URL" -X -tAc "select count(*) from pg_available_extensions where name = 'vector'" 2>/dev/null)"
  if [ "$RS_VECTOR" = "1" ]; then
    cp "$RS/sql/search_hybrid.sql" "$RS_APP/supabase/migrations/20991231000200_search_hybrid.sql"
    cp "$RS/sql/search_hybrid.test.sql" "$RS_APP/supabase/tests/database/search_hybrid.test.sql"
  fi
  check "recipe-search: the app's DB gate is green with the recipe in (migrations, advisors, pgTAP, negative control)" \
    "cd '$RS_APP' && DATABASE_URL='$RS_URL' ./scripts/db-test.sh"
  # rs_tap_plant <plant sql> <test file> <needle>...: plant in a rolled-back transaction,
  # run one pgTAP file, and require each named assertion to fail.
  _rs_tap_plant() {
    local plant="$1" tf="$2" out n; shift 2
    out="$( { echo 'begin;'; cat "$plant"; cat "$tf"; } | psql "$RS_URL" -X -q -tA 2>&1)"
    for n in "$@"; do grep -q "^not ok $n " <<<"$out" || { printf '%s\n' "$out" | head -40; echo "assertion $n did not fail"; return 1; }; done
  }
  check "recipe-search: pgTAP fails a planted SECURITY DEFINER search_items() without a user filter (isolation tests 2 + 3 go red)" \
    "_rs_tap_plant '$RS/sql/negative_control.sql' '$RS/sql/search.test.sql' 1 2 3 11"
  sed -e 's/i\.user_id = (select auth\.uid())/true/' "$RS/sql/search.sql" > "$T/rs-fts-nofilter.sql"
  _rs_rls_backstop() {  # filter dropped, still invoker: RLS holds (2 passes), the no-uid call leaks (11 fails)
    local out
    _rs_tap_plant "$T/rs-fts-nofilter.sql" "$RS/sql/search.test.sql" 11 || return 1
    out="$( { echo 'begin;'; cat "$T/rs-fts-nofilter.sql" "$RS/sql/search.test.sql"; } | psql "$RS_URL" -X -q -tA 2>&1)"
    grep -q '^ok 2 ' <<<"$out" || { printf '%s\n' "$out" | head -30; return 1; }
  }
  check "recipe-search: with only the filter dropped, RLS still isolates users; the service-key test is what catches it" _rs_rls_backstop
  if [ "$RS_VECTOR" = "1" ]; then
    sed -e 's/security invoker/security definer/' -e 's/i\.user_id = (select auth\.uid())/true/' "$RS/sql/search_hybrid.sql" > "$T/rs-hyb-leak.sql"
    check "recipe-search: pgTAP fails the same planted rewrite of search_items_hybrid()" \
      "_rs_tap_plant '$T/rs-hyb-leak.sql' '$RS/sql/search_hybrid.test.sql' 1 2 7"
  else
    skip "recipe-search: hybrid (pgvector) migration + pgTAP, and its planted definer" "the pgvector extension (apt: postgresql-<ver>-pgvector)"
  fi
  psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "drop database if exists $RS_DB" >/dev/null 2>&1 || true
else
  skip "recipe-search: DB gate with the recipe in, and pgTAP fails a planted definer search (FTS + hybrid)" "APPBOX_SELFTEST_DATABASE_URL (Postgres + pgTAP + pgvector)"
fi
