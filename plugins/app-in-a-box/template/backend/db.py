"""Supabase service client (bypasses RLS, so scope every query by user id).

`rpc()` calls a Postgres function: the ONLY way to make a multi-row write atomic.
Two `.update()` / `.insert()` calls are two HTTP requests and two transactions; if the
second fails, the data is half-changed. A function body runs in one transaction, so
it commits or rolls back as a whole. Pattern (see backend/AGENTS.md and the
`register_push_token` example in supabase/migrations):

    create or replace function public.do_thing(p_user_id uuid, ...) returns ...
    language plpgsql security definer set search_path = '' as $$ ... $$;
    revoke execute on function public.do_thing(uuid, ...) from public, anon, authenticated;
    grant execute on function public.do_thing(uuid, ...) to service_role;

    rpc(db, "do_thing", {"p_user_id": user.id, ...})   # user.id from the token, always
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status

from backend.config import feature_missing, supabase_service_key, supabase_url

logger = logging.getLogger(__name__)
_FEATURE = "database + auth (Supabase)"

# SQLSTATE raised by a function -> HTTP status. Raise these from plpgsql with
# `raise exception 'not_found' using errcode = 'P0002';` and the detail becomes the
# message. Anything else is a real 500 (with an error_id), never a guess.
RPC_ERRORS: dict[str, int] = {
    "42501": 403,  # insufficient_privilege: ownership check failed
    "P0002": 404,  # no_data_found
    "23505": 409,  # unique_violation
    "23514": 422,  # check_violation
    "22023": 422,  # invalid_parameter_value
}


@lru_cache(maxsize=1)
def _client() -> Any:
    from supabase import create_client

    return create_client(supabase_url(), supabase_service_key())


def get_db() -> Any:
    """FastAPI dependency. 503 with a named reason when Supabase isn't wired."""
    if feature_missing(_FEATURE):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{_FEATURE} not configured")
    return _client()


def rpc(db: Any, fn: str, params: dict[str, Any]) -> Any:
    """Call a Postgres function in one transaction and return its result.

    Maps the function's SQLSTATE to an HTTP error (RPC_ERRORS); unknown errors
    propagate to the global handler (500 + error_id).
    """
    try:
        return db.rpc(fn, params).execute().data
    except Exception as exc:
        code = getattr(exc, "code", None)
        if isinstance(code, str) and code in RPC_ERRORS:
            message = getattr(exc, "message", None) or "rpc_failed"
            raise HTTPException(RPC_ERRORS[code], str(message)) from exc
        logger.warning("rpc %s failed (%s)", fn, type(exc).__name__)
        raise
