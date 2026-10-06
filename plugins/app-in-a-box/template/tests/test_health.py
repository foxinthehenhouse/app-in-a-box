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


# --- production-only: email sign-in needs custom SMTP --------------------------------

_EMAIL = "email sign-in (custom SMTP)"


def test_production_health_names_email_when_smtp_is_missing(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    body = TestClient(create_app()).get("/health").json()
    assert body["status"] == "degraded"
    assert body["features_unavailable"][_EMAIL] == ["AUTH_SMTP_HOST"]


def test_production_health_stops_naming_email_once_smtp_is_wired(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SMTP_HOST", "smtp.resend.com")
    body = TestClient(create_app()).get("/health").json()
    assert _EMAIL not in body["features_unavailable"]
    assert "smtp.resend.com" not in str(body)  # names only, never values


def test_email_is_not_required_outside_production() -> None:
    # Local `supabase start` catches mail itself, and APP_ENV here is "test".
    assert _EMAIL not in check_feature_config()
    assert feature_missing(_EMAIL) == ["AUTH_SMTP_HOST"]  # still answerable by name


def test_smtp_and_other_features_are_scoped_apart(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SMTP_HOST", "smtp.resend.com")
    missing = check_feature_config()
    assert _EMAIL not in missing
    assert "database + auth (Supabase)" in missing
    monkeypatch.delenv("AUTH_SMTP_HOST")
    monkeypatch.setenv("SUPABASE_URL", "x")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "x")
    missing = check_feature_config()
    assert "database + auth (Supabase)" not in missing
    assert _EMAIL in missing


def test_health_status_reads_as_the_uptime_keyword(monkeypatch) -> None:
    # The uptime monitor (provision step 8) alerts when the body lacks `"status":"ok"`,
    # byte for byte. Pretty-printed or reordered JSON would page the owner all night.
    # Wire every registered feature (a recipe may add its own), then unwire one.
    for need in FEATURE_CONFIG.values():
        for name in need:
            monkeypatch.setenv(name if isinstance(name, str) else name[0], "x")
    assert '"status":"ok"' in TestClient(create_app()).get("/health").text
    monkeypatch.delenv("SUPABASE_URL")
    assert '"status":"ok"' not in TestClient(create_app()).get("/health").text
