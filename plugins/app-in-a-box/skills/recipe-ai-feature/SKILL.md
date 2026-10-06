---
name: recipe-ai-feature
description: Add an LLM-powered feature to an App in a Box app the safe way - one fenced backend module, registered in FEATURE_CONFIG, pinned SDK, a per-user daily cost cap in Postgres, an eval set, and honest failure (no fake answers). Includes a ready reference for answers grounded in the user's own content (pgvector RAG with RLS-respecting retrieval, citations, optional Langfuse tracing). Use when the owner asks for AI, a chatbot, summaries, suggestions, "ask my notes", search by meaning, "use Claude", "generate", or any feature that calls a model API.
---

# Recipe: an AI feature (fenced, capped, evaluated)

`$KIT` is the plugin root: `appbox.yaml` → `kit_root` if present, else
`${CLAUDE_PLUGIN_ROOT}` (Claude Code) or the folder two levels above this file (Codex /
pasted prompt).

LLM calls live in exactly one module, `backend/services/ai_<feature>.py`, named in the
AI fence in `AGENTS.md` (critical rule 8). The client never calls a model directly and
never holds a model key.

⚖️ Owner decisions: which model (quality vs cost), the per-user daily cap, and whether
user content may be sent to the provider (update the privacy policy and the store
privacy labels if so). With retrieval, also: which embeddings provider, and whether
traces may contain text (off by default).

**Answers from the user's own content?** (their notes, entries, documents: "ask my
notes", "find the one about...") Use the reference in
`$KIT/skills/recipe-ai-feature/reference/` and the Retrieval section below. It is the
steps here, already built and tested. For a feature with no retrieval (a summary of one
item, a suggestion), follow the steps and keep the same shape.

## Steps

1. **Fence**: set `AGENTS.md` rule 8 to "Claude API only in `backend/services/ai_<feature>*`.",
   then let that module through the checked fence: in `pyproject.toml`, the "LLM SDKs are
   fenced" contract gets `ignore_imports = ["backend.services.ai_<feature> -> anthropic"]`
   (one line per module that imports the SDK). `lint-imports` (CI) fails an SDK import
   anywhere else, and fails an entry that matches no import, so the fence stays exact.
2. **Pin the SDK**: `anthropic>=X.Y,<X+1` in `requirements.txt` with a real upper bound
   (a real app shipped a broken production when a floating pin pulled a new major that
   removed a parameter). `test_every_requirement_has_an_upper_bound` enforces it.
3. **Config**: `backend/config.py` → `"ai (Anthropic)": ("ANTHROPIC_API_KEY",)` in
   `FEATURE_CONFIG`. The route guards with `feature_missing("ai (Anthropic)")` → 503
   naming the feature.
4. **Module** `backend/services/ai_<feature>.py`:
   - builds the prompt from **server-side** data (queries scoped by `user.id`), with
     user text passed as clearly delimited data, never as instructions;
   - one call with a timeout (e.g. 30 s) and `max_tokens` set; model id in one constant
     (overridable with `AI_MODEL`);
   - parses output into a Pydantic model; on a parse/API failure raises a typed error.
     **Never** return a canned "friendly" answer that looks like a real one: the API
     returns 503/502 `{"detail": "ai_unavailable"}` and the app shows an honest retry.
   - Before editing, check current model ids/params with the `claude-api` skill (or the
     provider docs), not memory.
5. **Cost cap** (Postgres, not memory): migration with `ai_usage (user_id, day,
   input_tokens, output_tokens, primary key (user_id, day))`, RLS on, service-only, and
   an atomic `ai_usage_add(p_user_id, p_in, p_out, p_cap)` function that adds and returns
   whether the user is still under the cap. Check before the call (429
   `ai_daily_limit`), record actual usage after. Also `rate_limit("ai.<feature>", 10)` on
   the route. The reference ships this migration. Each migration changes the schema:
   refresh the snapshot with `DATABASE_URL=... scripts/db-test.sh --write-snapshot` and
   commit `supabase/schema-snapshot.txt` with it.
6. **Route** `POST /api/v1/<feature>` with the guard, rate limit, cap, and a response
   `Wire` model mirrored in `mobile/lib/api.ts`.
7. **Evals** `tests/evals/<feature>/cases.jsonl`: 10-30 real-ish inputs with assertions
   (schema valid, must/must-not contain, length). The default suite runs them against
   recorded outputs, so prompt-building and parsing stay covered for free; a live run
   against the real API is opt-in (it costs money).
8. **Mobile**: loading state with a skeleton, an honest error with retry, and analytics
   `aiRequested`, `aiSucceeded({ duration_ms })`, `aiFailed({ error_code })`.

## Retrieval: answers grounded in the user's own content

The reference is a complete "Ask your notes" feature: the user's text is chunked and
embedded, stored in Postgres with pgvector, and a question is answered from the closest
chunks **of that user only**, with citations back to the notes it used.

### Install it

```bash
python3 "$KIT/skills/recipe-ai-feature/reference/install.py" .   # from the app root
pip install -r requirements.txt && python -m pytest -q
```

It copies the files and makes every wiring edit the app's guards demand (fence, map
row, FEATURE_CONFIG, router, data export, wire contract + `mobile/lib/api.ts` types,
test env, SDK pin, pgvector in the DB workflow, `.env.example`). When an anchor is
missing because the app has moved on from the template, it lists the edit for you to
make by hand and exits 1. Then rename `ask` / "notes" to the app's domain (keep the
`ai_` prefix on the module: it is what the fence names), and call `index_source()` /
`remove_source()` wherever the user saves or deletes that content.

| File | What it is |
|---|---|
| `backend/services/ai_ask.py` | The fenced module: chunking, `Embedder` / `Generator` interfaces, `UserDB` (the caller's JWT), prompt, grounding, cap, tracing |
| `backend/routers/ask.py` | `PUT/DELETE /api/v1/ask/sources/{id}`, `POST /api/v1/ask`; 503 / 429 / 502 mapping |
| `supabase/migrations/*_ai_usage.sql` | The cost cap (step 5) |
| `supabase/migrations/*_ai_chunks.sql` | `ai_chunks` (`vector(1024)`, HNSW), RLS, `ai_chunks_replace` + `ai_match_chunks` (security invoker) |
| `supabase/tests/database/ai_chunks.test.sql` | pgTAP: user B never retrieves user A's chunks; the service key gets nothing |
| `tests/test_ai_ask.py` | Fence, isolation, cap, grounding, honest failure, chunking, tracing, evals |
| `tests/evals/ask/cases.jsonl` | 10 cases, incl. grounded answers, not-in-notes and prompt injection |

### How isolation works (don't weaken it)

The backend normally talks to Supabase with the service key, which **bypasses RLS**. A
retrieval query run that way returns the nearest chunks from *every* user: a cross-user
leak with a search box. So retrieval never uses the service key:

- **RLS** on `ai_chunks`: owner-only select / insert / delete.
- **Security invoker functions** that also filter `user_id = (select auth.uid())`.
  Invoker means RLS applies; the explicit filter means a service-key caller (no
  `auth.uid()`) gets zero rows instead of everyone's.
- **The caller's JWT**: `UserDB` calls PostgREST with the signed-in user's token, and
  `SUPABASE_ANON_KEY` (the publishable key) as the gateway key. The only service-key
  call on the AI path is the cost cap, keyed by the verified `user.id`.

Guards that fail on a planted leak:

| Leak | Caught by |
|---|---|
| A `security definer` retrieval function, one without the `auth.uid()` filter, or a view without `security_invoker` | `tests/test_migrations_static.py` (in every app; dormant until a `vector` column exists) |
| A vector table with no HNSW index | `tests/test_migrations_static.py` |
| A service-key `.table("ai_chunks")` read without `.eq("user_id", user.id)` | `tests/test_scoping_static.py` |
| Retrieval called on anything but `user_db`, or the model SDK outside `ai_ask*` | `tests/test_ai_ask.py::test_the_fence_holds` |
| Policies or functions letting B see A's rows on a real Postgres | `supabase/tests/database/ai_chunks.test.sql` (DB workflow) |

Content shared within an organisation is a different design: an `org_id`, a membership
table, and policies on membership. Write it up in `docs/decision-log.md` before building it.

### Providers

Anthropic has no embeddings API. `Embedder` speaks the OpenAI-compatible `/embeddings`
shape, so one class covers:

- **Voyage AI** (the default, `EMBEDDINGS_BASE_URL` unset): `voyage-3.5-lite` at 1024
  dimensions, with a free tier for small apps. Queries and documents are embedded with
  the right `input_type`.
- **OpenAI** (`https://api.openai.com/v1`): pick a model that returns 1024 dimensions,
  or change the column.
- **Local** (Ollama, text-embeddings-inference: `http://host:port/v1`), with any
  non-empty `EMBEDDINGS_API_KEY`.

The vector column is sized to `EMBEDDINGS_DIM` (1024), and a wrong-sized vector is a
502, not a silent insert. Changing the model means a new column, a backfill and a swap,
never an in-place change. Generation is `Generator`, Claude by default, with the model
in `AI_MODEL` (falls back to `DEFAULT_MODEL`).

### Grounding and citations

The prompt numbers each retrieved chunk as a `<source>`; the model must cite `[n]` or
answer exactly `NOT_IN_NOTES`. `parse_answer()` refuses (502) an answer citing a source
it was never given, a "found" answer with no citation, or a mix of both. Nothing
retrieved → `found: false` without calling the model, so it costs nothing. The client
gets `citations: [{index, sourceId, title, snippet}]`: show them, they are what makes
the answer trustworthy.

The eval set's `grounded` assertion checks each expected fact is in the answer **and**
in a source the answer cites, not just somewhere in the prompt. Live run:
`RUN_LIVE_EVALS=1 EVAL_ANTHROPIC_API_KEY=... python -m pytest -q tests/test_ai_ask.py -k live`.

### Tracing (optional)

⚖️ Off by default. Two routes:

- **Langfuse** (MIT; free cloud tier; self-hosting needs ClickHouse): run
  `install.py --tracing`, or add `"ai tracing (Langfuse)": ("LANGFUSE_PUBLIC_KEY",
  "LANGFUSE_SECRET_KEY")` to `FEATURE_CONFIG` yourself, so `/health` reports it when
  the keys go missing. Tracing switches on only when that entry exists: keys alone do
  nothing. `LANGFUSE_HOST` for the EU region or self-hosting.
- **PostHog LLM analytics** (no new vendor, if the app already uses PostHog): send a
  `$ai_generation` event from the backend with the fields `trace_payload()` builds.

Either way, traces carry **no user text and no user id by default**: model, tokens,
latency, chunk ids, similarities, outcome and the request id (which joins the logs and
Sentry). `AI_TRACE_CONTENT=1` adds the question and answer. That makes the tracing
vendor a processor of user content, so update the privacy policy and the store privacy
labels first. It's the same rule as the Sentry scrubbing in `backend/observability.py`.

## Env / wiring checklist

| Where | What |
|---|---|
| Railway | `railway variables --set "ANTHROPIC_API_KEY=..."` (production + any preview env); with retrieval also `EMBEDDINGS_API_KEY` and `SUPABASE_ANON_KEY`, optionally `EMBEDDINGS_BASE_URL` / `EMBEDDINGS_MODEL` / `AI_MODEL` / `AI_DAILY_TOKEN_CAP` |
| FEATURE_CONFIG | `"ai (Anthropic)": ("ANTHROPIC_API_KEY",)`; retrieval: `"ai retrieval (embeddings)": ("EMBEDDINGS_API_KEY", "SUPABASE_ANON_KEY")`; tracing only once it's turned on |
| `conftest.py` | add the AI vars to the blanked vars so tests never call a provider |
| Supabase | the `vector` extension (the migration enables it); pgvector >= 0.8 for `hnsw.iterative_scan` |
| DB workflow | `postgresql-<v>-pgvector` next to pgTAP, so the migration applies in CI |
| EAS | nothing (the app never sees a key) |
| Provider consoles | a monthly spend limit on each (model and embeddings) as the last line of defence |

## Tests to add

- 503 naming "ai (Anthropic)" when the key is missing; the route doesn't reach the SDK.
- Scoping: the prompt contains only the caller's rows (filter-honouring fake); with
  retrieval, the retrieval request carries the caller's JWT and never the service key.
- Cap: under-cap call proceeds; over-cap returns 429 before any SDK call; usage is
  recorded after success; two app instances share the cap (DB-backed). Indexing is capped too.
- Failure honesty: an SDK exception → 502/503 `ai_unavailable`, never a 200 with filler;
  an ungrounded answer is a 502, not a 200.
- SDK signature: `inspect.signature` of the method you call accepts every kwarg you
  pass (catches a breaking SDK bump in CI, not in production).
- Evals: fixture run in the default suite, including a grounded-answer case; live run opt-in.

## Done means

- [ ] `/health` in production lists no `ai (...)` gap.
- [ ] A real request returns a schema-valid answer; with the key removed it returns
      503 and the app shows retry, not a fake answer.
- [ ] Exceeding the daily cap returns 429 and the app explains it kindly.
- [ ] Live eval run passes its threshold; the fixture eval runs in CI.
- [ ] With retrieval: the DB workflow's pgTAP run is green (user B can't retrieve user
      A's chunks), and the app shows each answer's citations.
