"""Privacy-safe Sentry setup, request ids and logging.

Sentry is an operational error sink, not a second copy of user data. Events are
stripped of request bodies, identity, messages, breadcrumbs and exception values
before they leave the process. The type and stack trace are enough to diagnose.
Sentry is a no-op without SENTRY_DSN or outside deployed environments.

Every request carries a request id (the caller's `X-Request-ID` if it's sane, else a
fresh one). It is echoed on the response, stamped on every log line, and tagged on
Sentry events, so one id joins the client error, the Railway logs and the Sentry
issue. `LOG_FORMAT=json` switches logs to one JSON object per line.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any

from backend.config import app_env, env

logger = logging.getLogger(__name__)

_NON_DEPLOY = {"", "dev", "development", "local", "test", "testing"}
_KEPT_TAGS = ("error_id", "request_id")

# Per-request (contextvars are task-local), so this is NOT cross-request state.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


def new_request_id(incoming: str | None) -> str:
    """Trust a caller-supplied id only if it is short and inert (it lands in logs)."""
    if incoming and _REQUEST_ID_RE.match(incoming):
        return incoming
    return uuid.uuid4().hex


def current_request_id() -> str:
    return request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: what Railway / Datadog / Axiom parse natively."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Idempotent: safe to call from every create_app()."""
    root = logging.getLogger()
    handler = next((h for h in root.handlers if getattr(h, "_appbox", False)), None)
    if handler is None:
        handler = logging.StreamHandler()
        handler._appbox = True  # type: ignore[attr-defined]
        handler.addFilter(_RequestIdFilter())
        root.addHandler(handler)
    if env("LOG_FORMAT").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s")
        )
    root.setLevel(env("LOG_LEVEL", "INFO").upper())


def scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    for key in ("user", "message", "logentry", "extra", "contexts", "breadcrumbs"):
        event.pop(key, None)
    tags = event.get("tags")
    kept = (
        {k: tags[k] for k in _KEPT_TAGS if isinstance(tags.get(k), str)}
        if isinstance(tags, dict)
        else {}
    )
    if kept:
        event["tags"] = kept
    else:
        event.pop("tags", None)
    exception = event.get("exception")
    if isinstance(exception, dict) and isinstance(exception.get("values"), list):
        for value in exception["values"]:
            if isinstance(value, dict):
                value["value"] = "Details removed by privacy policy"
    request = event.get("request")
    if isinstance(request, dict):
        event["request"] = {"method": request["method"]} if "method" in request else {}
    return event


def init_sentry() -> bool:
    dsn = env("SENTRY_DSN")
    environment = env("SENTRY_ENVIRONMENT") or app_env()
    if not dsn or environment in _NON_DEPLOY:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=env("SENTRY_RELEASE") or env("RAILWAY_GIT_COMMIT_SHA") or None,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=scrub_event,
    )
    logger.info("Sentry initialised for %s", environment)
    return True


def tag_request(request_id: str) -> None:
    """Tag every Sentry event raised while this request is in flight."""
    try:
        import sentry_sdk

        sentry_sdk.get_isolation_scope().set_tag("request_id", request_id)
    except Exception:  # never let monitoring break a request
        logger.debug("sentry tag failed", exc_info=True)


def capture_exception(exc: BaseException, error_id: str) -> None:
    try:
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("error_id", error_id)
            scope.set_tag("request_id", request_id_var.get())
            sentry_sdk.capture_exception(exc)
    except Exception:  # never let monitoring break a response
        logger.debug("sentry capture failed", exc_info=True)
