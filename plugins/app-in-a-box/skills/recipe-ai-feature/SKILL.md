---
name: recipe-ai-feature
description: Add an LLM-powered feature to an App in a Box app the safe way - one fenced backend module, registered in FEATURE_CONFIG, pinned SDK, a per-user daily cost cap in Postgres, an eval set, and honest failure (no fake answers). Use when the owner asks for AI, a chatbot, summaries, suggestions, "use Claude", "generate", or any feature that calls a model API.
---

# Recipe: an AI feature (fenced, capped, evaluated)

LLM calls live in exactly one module, `backend/services/ai_<feature>.py`, named in the
AI fence in `AGENTS.md` (critical rule 8). The client never calls a model directly and
never holds a model key.

⚖️ Owner decisions: which model (quality vs cost), the per-user daily cap, and whether
user content may be sent to the provider (update the privacy policy and the store
privacy labels if so).

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
   - one call with a timeout (e.g. 30 s) and `max_tokens` set; model id in one constant;
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
   the route.
6. **Route** `POST /api/v1/<feature>` with the guard, rate limit, cap, and a response
   `Wire` model mirrored in `mobile/lib/api.ts`.
7. **Evals** `tests/evals/<feature>/cases.jsonl`: 10-30 real-ish inputs with assertions
   (schema valid, must/must-not contain, length). A pytest marked `eval` runs them
   against the real API (opt-in, costs money); a default-run test runs them against a
   recorded fixture so prompt-building and parsing stay covered for free.
8. **Mobile**: loading state with a skeleton, an honest error with retry, and analytics
   `aiRequested`, `aiSucceeded({ duration_ms })`, `aiFailed({ error_code })`.

## Env / wiring checklist

| Where | What |
|---|---|
| Railway | `railway variables --set "ANTHROPIC_API_KEY=..."` (production + any preview env) |
| FEATURE_CONFIG | `"ai (Anthropic)": ("ANTHROPIC_API_KEY",)` |
| `conftest.py` | add `ANTHROPIC_API_KEY` to the blanked vars so tests never call the API |
| EAS | nothing (the app never sees the key) |
| Provider console | a monthly spend limit as the last line of defence |

## Tests to add

- 503 naming "ai (Anthropic)" when the key is missing; the route doesn't reach the SDK.
- Scoping: the prompt contains only the caller's rows (filter-honouring fake).
- Cap: under-cap call proceeds; over-cap returns 429 before any SDK call; usage is
  recorded after success; two app instances share the cap (DB-backed).
- Failure honesty: an SDK exception → 502/503 `ai_unavailable`, never a 200 with filler.
- SDK signature: `inspect.signature` of the method you call accepts every kwarg you
  pass (catches a breaking SDK bump in CI, not in production).
- Evals: fixture run in the default suite; live run with `-m eval`.

## Done means

- [ ] `/health` in production lists no `ai (Anthropic)` gap.
- [ ] A real request returns a schema-valid answer; with the key removed it returns
      503 and the app shows retry, not a fake answer.
- [ ] Exceeding the daily cap returns 429 and the app explains it kindly.
- [ ] Live eval run passes its threshold; the fixture eval runs in CI.
