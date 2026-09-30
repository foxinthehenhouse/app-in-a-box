"""Sentry privacy (backend/observability.py): error events must carry no user data.

Sentry is an operational sink, not a second copy of user data. These pin what leaves
the process: no identity, request bodies, messages or exception values; only the
error_id tag, the method and the stack.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend import observability


def _event() -> dict[str, Any]:
    return {
        "user": {"id": "u1", "email": "a@example.com"},
        "message": "failed for a@example.com",
        "logentry": {"message": "x"},
        "extra": {"body": "secret"},
        "contexts": {"x": 1},
        "breadcrumbs": [{"message": "typed their password"}],
        "tags": {"error_id": "e-1", "email": "a@example.com"},
        "exception": {"values": [{"type": "ValueError", "value": "bad email a@example.com"}]},
        "request": {"method": "POST", "data": {"password": "hunter2"}, "headers": {"a": "b"}},
    }


def test_scrub_removes_identity_and_payloads() -> None:
    out = observability.scrub_event(_event(), {})
    for key in ("user", "message", "logentry", "extra", "contexts", "breadcrumbs"):
        assert key not in out
    assert out["tags"] == {"error_id": "e-1"}
    assert out["request"] == {"method": "POST"}
    assert out["exception"]["values"][0] == {
        "type": "ValueError",
        "value": "Details removed by privacy policy",
    }
    assert "a@example.com" not in repr(out) and "hunter2" not in repr(out)


def test_scrub_without_error_id_drops_all_tags() -> None:
    event = _event()
    event["tags"] = {"email": "a@example.com"}
    event["request"] = {"url": "https://x/y?email=a@example.com"}
    out = observability.scrub_event(event, {})
    assert "tags" not in out and out["request"] == {}


def test_sentry_is_off_in_dev_and_without_a_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    assert observability.init_sentry() is False
    monkeypatch.setenv("SENTRY_DSN", "https://k@o.ingest.sentry.io/1")
    assert observability.init_sentry() is False  # APP_ENV=test


def test_sentry_init_in_production_is_privacy_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentry_sdk

    seen: dict[str, Any] = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    monkeypatch.setenv("SENTRY_DSN", "https://k@o.ingest.sentry.io/1")
    monkeypatch.setenv("APP_ENV", "production")
    assert observability.init_sentry() is True
    assert seen["send_default_pii"] is False
    assert seen["include_local_variables"] is False
    assert seen["max_request_body_size"] == "never"
    assert seen["before_send"] is observability.scrub_event


def test_capture_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentry_sdk

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("sentry down")

    monkeypatch.setattr(sentry_sdk, "capture_exception", boom)
    observability.capture_exception(ValueError("x"), "e-1")
