"""backend/db.py: a missing Supabase config is a named 503, never a crash or a None."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend import db


def test_get_db_without_config_is_a_named_503() -> None:
    with pytest.raises(HTTPException) as exc:
        db.get_db()
    assert exc.value.status_code == 503
    assert "Supabase" in str(exc.value.detail)


def test_get_db_builds_one_cached_service_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import supabase

    made: list[tuple[str, str]] = []
    monkeypatch.setattr(
        supabase, "create_client", lambda url, key: made.append((url, key)) or object()
    )
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb-key")
    db._client.cache_clear()
    try:
        first, second = db.get_db(), db.get_db()
    finally:
        db._client.cache_clear()
    assert first is second
    assert made == [("https://proj.supabase.co", "sb-key")]
