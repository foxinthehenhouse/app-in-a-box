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
    "EXPO_ACCESS_TOKEN",
    "CORS_ORIGINS",
    "LOG_FORMAT",
    "GIT_SHA",
    "RAILWAY_GIT_COMMIT_SHA",
    "APP_VERSION",
    "SENTRY_RELEASE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _FEATURE_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    os.environ.pop("SENTRY_ENVIRONMENT", None)
