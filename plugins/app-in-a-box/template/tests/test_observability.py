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
    assert seen["before_send_transaction"] is observability.scrub_transaction
    assert "traces_sample_rate" not in seen  # the sampler decides, never the caller
    sampler = seen["traces_sampler"]
    assert sampler({"asgi_scope": {"path": "/api/v1/me"}, "parent_sampled": True}) == 0.05
    assert sampler({"asgi_scope": {"path": "/health"}}) == 0.0


def test_capture_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentry_sdk

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("sentry down")

    monkeypatch.setattr(sentry_sdk, "capture_exception", boom)
    observability.capture_exception(ValueError("x"), "e-1")


# ---- tracing -----------------------------------------------------------------


def test_tracing_samples_low_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)
    assert 0 < observability.DEFAULT_TRACES_SAMPLE_RATE <= 0.1, (
        "backend tracing must stay a low sample by default: every span is billed"
    )
    assert observability.traces_sample_rate() == observability.DEFAULT_TRACES_SAMPLE_RATE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0.2", 0.2), ("0", 0.0), ("1", 0.25), ("-3", 0.0), ("lots", 0.05), ("nan", 0.05)],
)
def test_traces_sample_rate_is_clamped(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: float
) -> None:
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", raw)
    assert observability.traces_sample_rate() == expected


def test_sampler_ignores_the_callers_decision() -> None:
    sampler = observability.make_traces_sampler(0.05)
    assert sampler({"asgi_scope": {"path": "/api/v1/me"}, "parent_sampled": True}) == 0.05
    assert sampler({"asgi_scope": {"path": "/api/v1/me"}, "parent_sampled": False}) == 0.05
    assert sampler({"asgi_scope": {"path": "/health"}}) == 0.0
    assert sampler({}) == 0.05


def test_errors_keep_their_trace_ids_and_nothing_else() -> None:
    event = _event()
    event["contexts"] = {
        "trace": {"trace_id": "a" * 32, "span_id": "b" * 16, "data": {"url": "x?email=a"}},
        "os": {"name": "Linux"},
    }
    out = observability.scrub_event(event, {})
    assert out["contexts"] == {"trace": {"trace_id": "a" * 32, "span_id": "b" * 16}}


def test_transactions_are_scrubbed_like_errors() -> None:
    txn = {
        "type": "transaction",
        "transaction": "/api/v1/me",
        "user": {"id": "u1", "email": "a@example.com"},
        "request": {"method": "GET", "url": "https://api/x?email=a@example.com", "headers": {}},
        "tags": {"request_id": "r-1", "email": "a@example.com"},
        "contexts": {"trace": {"trace_id": "c" * 32, "span_id": "d" * 16, "op": "http.server"}},
        "spans": [
            {
                "op": "http.client",
                "description": "GET https://x.supabase.co/rest/v1/profiles?id=eq.u1",
                "data": {"http.query": "id=eq.u1"},
            },
            {"op": "db", "description": None, "tags": {"email": "a@example.com"}},
        ],
    }
    out = observability.scrub_transaction(txn, {})
    assert out["transaction"] == "/api/v1/me"
    assert out["request"] == {"method": "GET"} and "user" not in out
    assert out["tags"] == {"request_id": "r-1"}
    assert out["contexts"]["trace"]["trace_id"] == "c" * 32
    assert out["spans"][0] == {
        "op": "http.client",
        "description": "GET https://x.supabase.co/rest/v1/profiles",
    }
    assert "a@example.com" not in repr(out) and "u1" not in repr(out)


def test_cors_lets_a_web_client_send_the_trace_headers() -> None:
    from fastapi.testclient import TestClient

    from backend.main import create_app

    resp = TestClient(create_app()).options(
        "/api/v1/me",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "traceparent, sentry-trace, x-request-id",
        },
    )
    assert resp.status_code == 200
    allowed = resp.headers["access-control-allow-headers"].lower()
    assert "traceparent" in allowed and "sentry-trace" in allowed
