"""Capability checklist over the rendered repo: the production pieces exist and are
wired. Each assertion names the file a user would be missing."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "path",
    [
        "docs/runbooks/release.md",
        "docs/runbooks/rollback.md",
        "scripts/rollback-ota.sh",
        "docs/runbooks/incident.md",
        "docs/runbooks/secrets-rotation.md",
        "docs/runbooks/backup-restore.md",
        "scripts/backup-db.sh",
        "scripts/restore-drill.sh",
        ".github/workflows/backup.yml",
        "COST.md",
        "mobile/.eas/workflows/pr-preview.yml",
        "mobile/.eas/workflows/release.yml",
        "backend/services/push_service.py",
        "backend/ratelimit.py",
    ],
)
def test_production_file_exists(path: str) -> None:
    assert (ROOT / path).is_file(), path


def test_rollback_runbook_covers_every_layer() -> None:
    text = (ROOT / "docs/runbooks/rollback.md").read_text()
    for needle in ("eas update:rollback", "eas update:republish", "railway redeploy", "PITR"):
        assert needle in text, needle


def test_eas_workflows_use_fingerprints_and_the_right_jobs() -> None:
    preview = (ROOT / "mobile/.eas/workflows/pr-preview.yml").read_text()
    release = (ROOT / "mobile/.eas/workflows/release.yml").read_text()
    assert "type: fingerprint" in preview
    assert "type: update" in preview
    assert "pr-${{ github.event.pull_request.number }}" in preview
    assert "type: submit" in release
    assert "profile: production" in release


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("DELETE", "/api/v1/me"),
        ("POST", "/api/v1/me/push-token"),
        ("DELETE", "/api/v1/me/push-token"),
        ("GET", "/api/v1/me/export"),
        ("POST", "/internal/cron/weekly-digest"),
        ("POST", "/internal/cron/push-receipts"),
        ("POST", "/internal/cron/prune-rate-limits"),
    ],
)
def test_production_routes_are_mounted(method: str, path: str) -> None:
    # Unauthenticated: must reach the route's own guard (401/422/503), not 404/405.
    status = TestClient(create_app()).request(method, path, json={}).status_code
    assert status not in (404, 405), (method, path, status)


def test_health_is_cheap_by_default() -> None:
    body = TestClient(create_app()).get("/health").json()
    assert "db" not in body  # the platform probe never touches the database
