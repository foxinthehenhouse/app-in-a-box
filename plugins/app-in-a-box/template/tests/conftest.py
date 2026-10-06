import os

import pytest

# Tests never talk to real services: blank every feature var unless a test sets it.
_FEATURE_VARS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_ANON_KEY",
    "SENTRY_DSN",
    "CRON_SECRET",
    "AUTH_SMTP_HOST",
    "EXPO_ACCESS_TOKEN",
    "CORS_ORIGINS",
    "LOG_FORMAT",
    "GIT_SHA",
    "RAILWAY_GIT_COMMIT_SHA",
    "APP_VERSION",
    "SENTRY_RELEASE",
    "POSTHOG_ERASURE_KEY",
    "POSTHOG_PROJECT_ID",
    "POSTHOG_API_HOST",
    "SENTRY_ERASURE_TOKEN",
    "SENTRY_ORG",
    "SENTRY_PROJECTS",
    "SENTRY_API_URL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _FEATURE_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    os.environ.pop("SENTRY_ENVIRONMENT", None)


@pytest.fixture(autouse=True)
def _closed_circuits() -> None:
    # backend/http.py keeps one circuit breaker per upstream per process; a test that
    # trips one must not make the next test's calls fail fast.
    try:
        from backend import http as outbound
    except ImportError:  # a guard test copied out without backend/ (selftest plants)
        return
    outbound.reset_breakers()
