from fastapi.testclient import TestClient

from backend.config import FEATURE_CONFIG, check_feature_config, feature_missing
from backend.main import create_app


def test_health_is_200_and_names_missing_features() -> None:
    body = TestClient(create_app()).get("/health").json()
    assert body["status"] == "degraded"
    assert set(body["features_unavailable"]) == set(FEATURE_CONFIG)


def test_health_ok_when_everything_wired(monkeypatch) -> None:
    for name in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SENTRY_DSN"):
        monkeypatch.setenv(name, "x")
    body = TestClient(create_app()).get("/health").json()
    body.pop("version", None)  # present only when the deploy sets a git sha
    assert body == {"status": "ok", "service": "__APP_SLUG__-api"}


def test_any_of_requirement_accepts_either_name(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "k")
    assert feature_missing("database + auth (Supabase)") == []


def test_feature_checks_are_scoped_per_feature(monkeypatch) -> None:
    # Wiring one feature must not make another look wired (the blanket-check bug).
    monkeypatch.setenv("SENTRY_DSN", "x")
    missing = check_feature_config()
    assert "error monitoring (Sentry)" not in missing
    assert "database + auth (Supabase)" in missing


def test_health_never_leaks_values(monkeypatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://secret-value@example.ingest.sentry.io/1")
    text = TestClient(create_app()).get("/health").text
    assert "secret-value" not in text


def test_unhandled_errors_return_an_error_id() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/debug/sentry")
    assert resp.status_code == 500
    assert resp.json()["error"] == "internal_error"
    assert len(resp.json()["error_id"]) == 36
