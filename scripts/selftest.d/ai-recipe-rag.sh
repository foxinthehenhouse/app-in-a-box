# AI recipe, retrieval path (recipe-ai-feature: pgvector RAG with citations). Sourced by
# selftest.sh with $KIT, $APP (rendered app, cwd), $T and the check/refuses helpers.
#
# The recipe ships a reference implementation and install.py. Proven here on a COPY of
# the rendered app (never $APP itself: the areas after this one expect a pristine
# render): it installs cleanly and idempotently, the app's whole suite stays green with
# it, and every isolation / cost / grounding / privacy guard fails on a planted violation
# with its own message. With APPBOX_SELFTEST_DATABASE_URL (kit CI) the app's DB gate also
# runs the pgTAP cross-user test on real Postgres + pgvector, green and then planted.
RAG_SK="$KIT/skills/recipe-ai-feature"
RAG_REF="$RAG_SK/reference"
RAG="$T/rag-app"
RAG_PY="$APP/.venv/bin/python"
RAG_PT="'$RAG_PY' -m pytest -q -p no:cacheprovider -p no:warnings -p no:logging"

_rag_copy() {  # <dest>: a fresh copy of the rendered app
  rm -rf "$1" && cp -a "$APP" "$1"
}

_rag_sub() {  # <file> <old> <new>: a literal, single replace that must apply
  python3 - "$1" "$2" "$3" <<'PYEOF'
import sys
p, old, new = sys.argv[1:4]
s = open(p, encoding="utf-8").read()
if old not in s:
    sys.exit(f"plant anchor not found in {p}: {old!r}")
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
PYEOF
}

# _rag_leak <file> <old> <new> <pytest args>: plant, run the app's tests, restore. A plant
# whose anchor is gone returns 0 ("still green"), so it can never pass as caught.
_rag_leak() {
  local f="$1" out rc
  cp "$f" "$T/rag-plant.bak"
  if ! _rag_sub "$f" "$2" "$3"; then cp "$T/rag-plant.bak" "$f"; return 0; fi
  out=$(cd "$RAG" && eval "$RAG_PT $4" 2>&1); rc=$?
  cp "$T/rag-plant.bak" "$f"
  printf '%s\n' "$out"
  return "$rc"
}

check "ai recipe: SKILL.md documents the RAG path (pgvector + HNSW, RLS, security invoker, caller JWT, citations, grounded evals, tracing off by default)" \
  "grep -q 'pgvector' '$RAG_SK/SKILL.md' && grep -q 'HNSW' '$RAG_SK/SKILL.md' \
   && grep -q 'Security invoker functions' '$RAG_SK/SKILL.md' && grep -q 'bypasses RLS' '$RAG_SK/SKILL.md' \
   && grep -q 'reference/install.py' '$RAG_SK/SKILL.md' && grep -q 'citations: \[{index, sourceId, title, snippet}\]' '$RAG_SK/SKILL.md' \
   && grep -q 'Anthropic has no embeddings API' '$RAG_SK/SKILL.md' && grep -q 'no user text and no user id by default' '$RAG_SK/SKILL.md' \
   && grep -q 'ClickHouse' '$RAG_SK/SKILL.md' && grep -q 'PostHog LLM analytics' '$RAG_SK/SKILL.md' \
   && grep -q 'grounded' '$RAG_SK/SKILL.md'"
check "ai recipe: the reference ships the module, router, both migrations, pgTAP, tests and a grounded eval case" \
  "for f in backend/services/ai_ask.py backend/routers/ask.py supabase/tests/database/ai_chunks.test.sql \
     tests/test_ai_ask.py tests/evals/ask/cases.jsonl mobile/lib/api-ask.snippet.ts install.py; do [ -f '$RAG_REF/'\$f ] || { echo \"missing \$f\"; exit 1; }; done \
   && ls '$RAG_REF'/supabase/migrations/*_ai_usage.sql '$RAG_REF'/supabase/migrations/*_ai_chunks.sql >/dev/null \
   && grep -q '\"grounded\"' '$RAG_REF/tests/evals/ask/cases.jsonl' \
   && [ \"\$(grep -c . '$RAG_REF/tests/evals/ask/cases.jsonl')\" -ge 10 ]"
check "ai recipe: the template's embedding guards are dormant on a fresh app, and their negative controls pass" \
  "cd '$APP' && $RAG_PT tests/test_migrations_static.py -k embedding"

_rag_install() {  # fresh copy + install, then snapshot for the idempotency check
  _rag_copy "$RAG" && python3 "$RAG_REF/install.py" "$RAG" \
    && rm -rf "$T/rag-snap" && cp -a "$RAG" "$T/rag-snap"
}
check "ai recipe: install.py wires a rendered app and exits 0" "_rag_install"
check "ai recipe: install.py is idempotent (a second run changes nothing)" \
  "python3 '$RAG_REF/install.py' '$RAG' && diff -r --no-dereference '$T/rag-snap' '$RAG'"
check "ai recipe: install.py relocks the hashed deps with its SDK pin (the app installs from the lock)" \
  "grep -q '^anthropic==' '$RAG/requirements.lock' && grep -q '^anthropic==' '$RAG/requirements-dev.lock' \
   && (cd '$RAG' && python3 scripts/check_lock.py)"
check "ai recipe: the installed app's whole suite is green (fence, cap, grounding, evals, wire contract, export, map, migration guards) and ruff-clean" \
  "cd '$RAG' && $RAG_PT && '$APP/.venv/bin/ruff' check backend tests"
check "ai recipe: the installed migrations hold the RAG shape (vector column, HNSW, RLS, invoker + auth.uid() retrieval, service-only cap)" \
  "M='$RAG/supabase/migrations'; grep -q 'embedding extensions.vector(1024) not null' \$M/*_ai_chunks.sql \
   && grep -q 'using hnsw (embedding extensions.vector_cosine_ops)' \$M/*_ai_chunks.sql \
   && grep -q 'alter table public.ai_chunks enable row level security' \$M/*_ai_chunks.sql \
   && [ \"\$(grep -c '^security invoker' \$M/*_ai_chunks.sql)\" = 2 ] \
   && grep -q 'where c.user_id = (select auth.uid())' \$M/*_ai_chunks.sql \
   && grep -q 'grant execute on function public.ai_usage_add(uuid, integer, integer, integer) to service_role' \$M/*_ai_usage.sql"

_rag_partial() {  # an app that moved on from the template: install must say what it skipped
  local d="$T/rag-partial"
  _rag_copy "$d" && _rag_sub "$d/backend/routers/export.py" "# table -> scoped reader." "# readers" \
    && python3 "$RAG_REF/install.py" "$d"
}
refuses "ai recipe: install.py names an edit it couldn't anchor and exits 1 (no silent partial install)" \
  "_rag_partial" "backend/routers/export.py: add scoped readers for ai_chunks and ai_usage"

# ---- planted leaks: each must fail, on its own rule -----------------------------------------
RAG_MIG="$(ls "$RAG"/supabase/migrations/*_ai_chunks.sql 2>/dev/null | head -1)"
RAG_SVC="$RAG/backend/services/ai_ask.py"
RAG_INVOKER=$'security invoker\nset search_path = \'\'\nas $$\n  with nearest'
RAG_FILTER=$'    where c.user_id = (select auth.uid())\n'

refuses "ai recipe catches: a SECURITY DEFINER retrieval function with no user filter (cross-user leak)" \
  "_rag_leak '$RAG_MIG' \"\$RAG_INVOKER\" \"\${RAG_INVOKER/invoker/definer}\" tests/test_migrations_static.py" \
  "public.ai_match_chunks reads ai_chunks as security definer (bypasses RLS)"
refuses "ai recipe catches: a retrieval function that drops the auth.uid() filter (a service-key call would return everyone's)" \
  "_rag_leak '$RAG_MIG' \"\$RAG_FILTER\" '' tests/test_migrations_static.py" \
  "public.ai_match_chunks reads ai_chunks without filtering on auth.uid()"
refuses "ai recipe catches: a vector table with no HNSW index" \
  "_rag_leak '$RAG_MIG' 'create index if not exists ai_chunks_embedding_hnsw' '-- create index if not exists ai_chunks_embedding_hnsw' tests/test_migrations_static.py" \
  "vector tables with no HNSW index: ['ai_chunks']"
refuses "ai recipe catches: a service-key query on the chunks table without user scoping" \
  "_rag_leak '$RAG_SVC' 'def remove_source(' \$'def debug_chunks(db: Any) -> Any:\n    return db.table(\"ai_chunks\").select(\"*\").execute().data\n\n\ndef remove_source(' tests/test_scoping_static.py" \
  "backend/services/ai_ask.py:debug_chunks"
refuses "ai recipe catches: retrieval run on the service client instead of the caller's JWT" \
  "_rag_leak '$RAG_SVC' 'rows = user_db.rpc(' 'rows = db.rpc(' 'tests/test_ai_ask.py -k fence'" \
  "retrieval must run as the caller (user_db), not db"
refuses "ai recipe catches: the cost cap skipped on the RAG path" \
  "_rag_leak '$RAG_SVC' \$'    check_cap(db, user_id)\n    started' '    started' 'tests/test_ai_ask.py -k cap'" \
  "test_over_cap_is_429_before_any_provider_call"
refuses "ai recipe catches: an answer with no citation returned as if grounded" \
  "_rag_leak '$RAG_SVC' 'raise AIUnavailable(\"ai_ungrounded\")  # a claim with no source behind it' 'pass' 'tests/test_ai_ask.py -k ungrounded'" \
  "test_ungrounded_answers_are_refused_not_returned[no-citation]"
refuses "ai recipe catches: a recorded eval answer that cites the wrong note (grounded eval)" \
  "_rag_leak '$RAG/tests/evals/ask/cases.jsonl' 'The cabin wifi password is pinecone42 [2].' 'The cabin wifi password is pinecone42 [1].' 'tests/test_ai_ask.py -k eval_case'" \
  "'pinecone42' is not in any cited source (ungrounded)"
refuses "ai recipe catches: traces carrying user text by default (PII)" \
  "_rag_leak '$RAG_SVC' 'with_text = env(\"AI_TRACE_CONTENT\") == \"1\"' 'with_text = True' 'tests/test_ai_ask.py -k trace'" \
  "test_traces_carry_no_user_text_by_default"
refuses "ai recipe catches: tracing switched on by env keys alone (not registered in FEATURE_CONFIG)" \
  "_rag_leak '$RAG_SVC' 'return TRACING_FEATURE in FEATURE_CONFIG and not feature_missing(TRACING_FEATURE)' 'return bool(env(\"LANGFUSE_PUBLIC_KEY\"))' 'tests/test_ai_ask.py -k tracing'" \
  "test_tracing_is_off_unless_registered"
check "ai recipe: every plant was reverted (the installed app is green again)" \
  "diff -r --no-dereference -x __pycache__ -x .pytest_cache -x .ruff_cache '$T/rag-snap' '$RAG'"

_rag_tracing() {  # --tracing registers Langfuse, so /health reports it when its keys are missing
  local d="$T/rag-tracing"
  _rag_copy "$d" && python3 "$RAG_REF/install.py" "$d" --tracing \
    && grep -q '"ai tracing (Langfuse)": ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")' "$d/backend/config.py" \
    && (cd "$d" && "$RAG_PY" -c "from fastapi.testclient import TestClient; from backend.main import create_app; b = TestClient(create_app()).get('/health').json(); assert b['features_unavailable']['ai tracing (Langfuse)'] == ['LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY'], b") \
    && (cd "$d" && eval "$RAG_PT tests/test_ai_ask.py tests/test_health.py")
}
check "ai recipe: install.py --tracing registers Langfuse in FEATURE_CONFIG, /health names its keys, tests stay green" "_rag_tracing"

check "ai recipe: kit CI installs pgvector next to pgTAP (the DB check below needs it)" \
  "grep -q 'postgresql-\${PGV}-pgvector' '$KIT/../../.github/workflows/kit.yml'"

# Real Postgres: the installed app's DB gate (migrations, advisors, both pgTAP files incl.
# the cross-user retrieval test, negative control) green; then a definer retrieval
# function with no user filter must turn the pgTAP run red. Own databases, dropped after.
_rag_db() {  # <name> [plant]: db-test.sh on a fresh database
  local base="${APPBOX_SELFTEST_DATABASE_URL%/*}" db="aib_rag_$1_$$" out rc
  psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "drop database if exists $db" -c "create database $db" || return 1
  if [ "${2:-}" = plant ]; then
    cp "$RAG_MIG" "$T/rag-plant.bak"; cp "$RAG/supabase/schema-snapshot.txt" "$T/rag-snap.bak"
    _rag_sub "$RAG_MIG" "$RAG_INVOKER" "${RAG_INVOKER/invoker/definer}" && _rag_sub "$RAG_MIG" "$RAG_FILTER" "" \
      || { cp "$T/rag-plant.bak" "$RAG_MIG"; return 0; }
  fi
  # --write-snapshot: the skill refreshes supabase/schema-snapshot.txt with the migration,
  # so a planted run can only go red on pgTAP, never on schema drift.
  out=$(cd "$RAG" && DATABASE_URL="$base/$db" ./scripts/db-test.sh --write-snapshot 2>&1); rc=$?
  [ "${2:-}" = plant ] && cp "$T/rag-plant.bak" "$RAG_MIG" && cp "$T/rag-snap.bak" "$RAG/supabase/schema-snapshot.txt"
  psql "$APPBOX_SELFTEST_DATABASE_URL" -X -q -c "drop database if exists $db" >/dev/null 2>&1
  printf '%s\n' "$out"
  return "$rc"
}
if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ]; then
  check "ai recipe DB gate: migrations + pgvector + pgTAP cross-user retrieval test green on real Postgres" "_rag_db ok"
  refuses "ai recipe DB gate catches: a definer retrieval function with no user filter returns another user's chunks" \
    "_rag_db leak plant" "not ok 3 - another user's chunks never come back from retrieval"
else
  skip "ai recipe DB gate: pgTAP cross-user retrieval test, green and planted" "APPBOX_SELFTEST_DATABASE_URL (Postgres + pgTAP + pgvector)"
fi
cd "$APP" || true
