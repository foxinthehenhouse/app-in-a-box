# __APP_NAME__: backend

Auto-loaded under `backend/` (Claude Code via CLAUDE.md, Codex via AGENTS.md). See `../AGENTS.md`.

## Layout

- `main.py`: `create_app()` factory, global error handler (returns `error_id` +
  `request_id`), `/health` (`?deep=1` adds a DB ping and dormant features).
- `config.py`: `FEATURE_CONFIG`, the env contract. Every env-gated capability registers
  here so a missing var shows in `/health.features_unavailable`, never as a silent no-op.
  Guard call sites with `feature_missing("<that feature>")`, never a blanket check.
  `OPTIONAL_FEATURE_CONFIG` holds shipped-but-dormant capabilities (cron): same guard,
  but they don't degrade `/health` until you move them up. `PRODUCTION_FEATURE_CONFIG`
  counts only when `APP_ENV=production`: email sign-in, whose `AUTH_SMTP_HOST` marker
  says Supabase has custom SMTP (Supabase sends the email; the API never holds the key).
- `auth.py`: `get_current_user` verifies the Supabase JWT (JWKS, with an Auth API
  fallback). Returns `CurrentUser(id, email)`.
- `db.py`: `get_db` service client (bypasses RLS). **Filter every query by `user.id`.**
  `rpc(db, fn, params)` calls a Postgres function (atomic writes, below).
- `ratelimit.py`: `rate_limit(bucket, limit, window_seconds)` dependency, counted in
  Postgres. Put it on every write endpoint.
- `middleware.py`: request id (`X-Request-ID`) + security headers.
- `routers/`: I/O only. `me.py` (profile, account deletion), `push.py` (push tokens),
  `internal.py` (`/internal/cron/*`, shared-secret auth).
- `services/`: logic. `push_service.py` (Expo push), `jobs_service.py` (cron jobs).
- `observability.py`: Sentry with PII scrubbing, request-id logging, `LOG_FORMAT=json`.

**The layering is checked.** `lint-imports` (CI python job; locally
`scripts/dev-venv.sh lint-imports`) runs the contracts in `pyproject.toml`
`[tool.importlinter]`: `main` → `routers` → `services` → `db` → `config`, never upward
(indirect chains count), and no `anthropic` / `openai` import outside the one AI module
named in the fence's `ignore_imports`. A service that needs something from a router
takes it as an argument or moves it down; a broken contract prints the import and its line.

## Conventions

- Type hints on every function; Pydantic models at the boundary; Black, line length 100.
- Response models inherit `Wire` (camelCase aliases). When you add or change one,
  update the matching `*Wire` interface in `mobile/lib/api.ts` in the same PR.
- Request-body models inherit `WireIn` (`extra="forbid"`: an unknown field is a 422,
  never a silent drop) and are mirrored the same way; `tests/test_wire_contract.py`
  pairs both directions and fails on an unlisted body or response model.
- Read-only handlers are plain `def` (threadpool), not `async def` around blocking I/O.
- Never trust an id from the request body for ownership; it comes from the token.
- **Exact paths.** `redirect_slashes=False`: React Native drops `Authorization` on a
  307, so `/things/` and `/things` are different routes. Call the exact path.
- **No in-process state.** Railway runs several workers; a module-level dict is
  per-process and silently diverges. Cross-request state (rate limits, job claims,
  OAuth state, push tickets) goes in a Postgres table. `test_prod_hardening.py` fails on
  a lower-case module-level dict/list/set or a `global`.
- **Write endpoints are rate limited**: `dependencies=[Depends(rate_limit("thing.create", 30))]`.
- Errors: raise `HTTPException` with a stable `detail`; unhandled errors get an
  `error_id` the client can show and support can grep.
- Tests in `/tests`: every endpoint gets a test, and ownership tests use a
  filter-honouring fake (`tests/test_me.py`, `tests/test_prod_fakes.py`) so a missing
  `.eq()` fails.

## Atomic multi-row writes

Two `.update()` / `.insert()` calls are two HTTP requests and two transactions: if the
second fails, the data is half-changed. Anything that writes more than one row (or
reads-then-writes) goes in ONE Postgres function, called with `rpc()`. Worked example:
`register_push_token` in `supabase/migrations/20260315120000_push_tokens.sql`.

```sql
create or replace function public.move_item(p_user_id uuid, p_item uuid, p_to uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is not null and auth.uid() <> p_user_id then        -- user JWT? only yourself
    raise exception 'not your account' using errcode = '42501';     -- -> 403
  end if;
  if not exists (select 1 from public.lists where id = p_to and user_id = p_user_id) then
    raise exception 'list not found' using errcode = 'P0002';       -- target must be yours too
  end if;
  update public.items set list_id = p_to
   where id = p_item and user_id = p_user_id;                       -- ownership in the WHERE
  if not found then raise exception 'item not found' using errcode = 'P0002'; end if;  -- -> 404
  update public.lists set updated_at = now() where id = p_to and user_id = p_user_id;
end; $$;
revoke execute on function public.move_item(uuid, uuid, uuid) from public, anon, authenticated;
grant execute on function public.move_item(uuid, uuid, uuid) to service_role;
```

```python
rpc(db, "move_item", {"p_user_id": user.id, "p_item": item_id, "p_to": list_id})
```

Rules: `security definer` + `set search_path = ''` (fully-qualify names); `p_user_id`
from the token and in every `where`; raise with an errcode `db.RPC_ERRORS` maps (42501
403, P0002 404, 23505 409, 23514/22023 422); revoke from anon/authenticated. The static
tests in `tests/test_prod_migrations.py` enforce the last three.

## Push, cron, account deletion

- **Push:** the app registers its token with `POST /api/v1/me/push-token`; send with
  `push_service.send_to_user(db, user_id, title, body, data)`. Dead tokens are pruned
  from tickets and from receipts (`/internal/cron/push-receipts`).
- **Cron:** a job is a function in `services/jobs_service.py` that starts with
  `claim_run(db, job, period_key)` (idempotent per period), plus a route in
  `routers/internal.py`. Schedule it per `docs/runbooks/release.md`.
- **Account deletion:** `DELETE /api/v1/me` with `{"confirm": "DELETE"}` deletes the
  auth user; every table keyed `user_id ... references auth.users on delete cascade`
  goes with it. A new table that holds user data MUST cascade, and Storage objects
  must be deleted in `_delete_user_files()`.

## Migrations

`supabase/migrations/YYYYMMDDHHMMSS_name.sql`. Additive, RLS on every table, rollback
noted in the header, and never edit an applied migration. Apply with `supabase db push`.
Run the SQL for real with `DATABASE_URL=<throwaway pg> scripts/dev-venv.sh python -m
pytest -m integration tests/test_prod_migrations.py`.
