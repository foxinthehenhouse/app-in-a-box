"""__APP_NAME__ API. Run `./run.sh` locally, and Railway runs the same factory."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()  # local dev only; deployed envs set real variables

from backend.config import (  # noqa: E402
    app_version,
    check_feature_config,
    cors_origins,
    feature_missing,
    is_production,
)
from backend.idempotency import (  # noqa: E402
    IdempotencyMiddleware,
    IdempotentReplay,
    replay_response,
)
from backend.middleware import RequestContextMiddleware  # noqa: E402
from backend.observability import (  # noqa: E402
    capture_exception,
    configure_logging,
    current_request_id,
    init_sentry,
)
from backend.routers import export, internal, me, push  # noqa: E402

logger = logging.getLogger("__APP_SLUG__")

SERVICE = "__APP_SLUG__-api"
_DB_FEATURE = "database + auth (Supabase)"


def _db_ping() -> str:
    """One cheap round trip to Postgres. Only on /health?deep=1, never the platform probe."""
    if feature_missing(_DB_FEATURE):
        return "unconfigured"
    try:
        from backend.db import get_db

        get_db().table("keep_alive").select("id").limit(1).execute()
        return "ok"
    except Exception as exc:
        logger.warning("deep health db ping failed (%s)", type(exc).__name__)
        return "error"


def create_app() -> FastAPI:
    configure_logging()
    init_sentry()
    prod = is_production()
    app = FastAPI(
        title="__APP_NAME__ API",
        # RN fetch follows a 307 but DROPS the Authorization header, so a trailing-slash
        # redirect turns into a 401 and a surprise sign-out. Exact paths only.
        redirect_slashes=False,
        docs_url=None if prod else "/docs",
        redoc_url=None,
        openapi_url=None if prod else "/openapi.json",
    )
    # Native apps send no Origin and never need CORS; this only admits browser clients
    # listed in CORS_ORIGINS (default: none in production, local Expo web elsewhere).
    # Bearer tokens, not cookies, so credentials stay off.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        # traceparent + sentry-trace: the trace ids the app sends (backend/observability.py).
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "Idempotency-Key",
            "traceparent",
            "sentry-trace",
        ],
        expose_headers=[
            "X-Request-ID",
            "Retry-After",
            "RateLimit",
            "RateLimit-Policy",
            "Idempotent-Replayed",
        ],
        allow_credentials=False,
    )
    # Inside the request-id middleware: holds a claimed idempotent write's response until
    # it is stored (backend/idempotency.py). Untouched requests pass straight through.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RequestContextMiddleware, hsts=prod)  # outermost: ids every request
    app.add_exception_handler(IdempotentReplay, replay_response)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        error_id = str(uuid.uuid4())
        request_id = current_request_id()
        logger.exception("unhandled error %s on %s", error_id, request.url.path)
        capture_exception(exc, error_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "error_id": error_id,
                "request_id": request_id,
                "path": request.url.path,
            },
            headers={"X-Request-ID": request_id},
        )

    @app.get("/health")
    def health(deep: bool = False) -> dict[str, Any]:
        """Always 200 so the platform healthcheck passes. `status` says what's wired.

        `?deep=1` also pings the database and lists dormant optional features.
        """
        missing = check_feature_config()
        body: dict[str, Any] = {"status": "degraded" if missing else "ok", "service": SERVICE}
        version = app_version()
        if version:
            body["version"] = version
        if missing:
            body["features_unavailable"] = missing
        if deep:
            body["db"] = _db_ping()
            if body["db"] == "error":
                body["status"] = "degraded"
            optional = check_feature_config(optional=True)
            if optional:
                body["features_optional_unconfigured"] = optional
        return body

    if not prod:

        @app.get("/debug/sentry", include_in_schema=False)
        def debug_sentry() -> None:
            raise RuntimeError("Sentry wiring check")

    app.include_router(me.router)
    app.include_router(push.router)
    app.include_router(export.router)
    app.include_router(internal.router)
    return app


app = create_app()
