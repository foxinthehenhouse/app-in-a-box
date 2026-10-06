"""Image uploads (recipe-uploads): signed URLs, per-user paths, limits, deletion, export.

Uses the filter-honouring fake (tests/test_prod_fakes.py), whose Storage `list()` only
returns the folder asked for, so a path built from anything but the verified user id
touches someone else's files and these tests fail. The SQL itself (bucket,
storage.objects policies, record_upload) is tested by pgTAP in
supabase/tests/database/uploads.test.sql.
"""

from __future__ import annotations

import re
import typing
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import uploads as uploads_router
from backend.services import uploads_service
from backend.services.uploads_service import ALLOWED_TYPES, BUCKET, MAX_BYTES
from tests.test_prod_fakes import (
    FakeAPIError,
    FakeBucket,
    FakeDB,
    clear_prod_env,
    client_for,
)
from tests.test_wire_contract import _api_routes

ROOT = Path(__file__).resolve().parents[1]
A = "aaaaaaaa-1111-4111-8111-111111111111"
B = "bbbbbbbb-2222-4222-8222-222222222222"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)


class UploadsDB(FakeDB):
    """FakeDB plus a stand-in for public.record_upload (the SQL is pgTAP-tested)."""

    @property
    def files(self) -> dict[str, dict[str, Any]]:
        return self.storage.objects.setdefault(BUCKET, {})

    def put(
        self, user_id: str, name: str, size: int = 2048, mimetype: str = "image/jpeg"
    ) -> str:
        path = f"{user_id}/{name}"
        self.files[path] = {"size": size, "mimetype": mimetype}
        return path

    def ops(self, op: str) -> list[str]:
        return [p for b, o, p in self.storage.calls if b == BUCKET and o == op]

    def _rpc_record_upload(
        self,
        p_user_id: str,
        p_upload_id: str,
        p_max_bytes: int,
        p_allowed_types: list[str],
    ) -> dict[str, Any]:
        path = f"{p_user_id}/{p_upload_id}"
        meta = self.files.get(path)
        if meta is None:
            raise FakeAPIError("P0002", "upload_not_found")
        if (
            not 0 < int(meta["size"]) <= p_max_bytes
            or meta["mimetype"] not in p_allowed_types
        ):
            raise FakeAPIError("23514", "upload_rejected")
        rows = self.tables.setdefault("uploads", [])
        row = next((r for r in rows if r["id"] == p_upload_id), None)
        if row is None:
            row = {
                "id": p_upload_id,
                "user_id": p_user_id,
                "path": path,
                "content_type": meta["mimetype"],
                "size_bytes": meta["size"],
                "created_at": f"2026-10-04T10:00:{len(rows):02d}+00:00",
            }
            rows.append(row)
        return dict(row)


def _ticket(client: TestClient, **body: Any) -> Any:
    payload = {"contentType": "image/jpeg", "sizeBytes": 2048, **body}
    return client.post("/api/v1/uploads", json=payload)


def _complete(db: UploadsDB, user: str, upload_id: str) -> Any:
    return client_for(db, user).post(f"/api/v1/uploads/{upload_id}/complete")


# ---- auth + rate limits -----------------------------------------------------------------

UPLOAD_ID = str(uuid.UUID(int=7))
ROUTES = [
    ("POST", "/api/v1/uploads"),
    ("POST", f"/api/v1/uploads/{UPLOAD_ID}/complete"),
    ("GET", "/api/v1/uploads"),
    ("DELETE", f"/api/v1/uploads/{UPLOAD_ID}"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_every_route_requires_auth(method: str, path: str) -> None:
    assert TestClient(create_app()).request(method, path).status_code == 401


def test_every_upload_route_is_rate_limited() -> None:
    routes = [
        r
        for r in _api_routes(create_app().routes)
        if r.path.startswith("/api/v1/uploads")
    ]
    assert len(routes) == len(ROUTES)
    for route in routes:
        names = [getattr(d.dependency, "__qualname__", "") for d in route.dependencies]
        assert any(
            n.startswith("rate_limit.") for n in names
        ), f"{route.path}: no rate_limit"


def test_minting_upload_urls_is_rate_limited() -> None:
    client = client_for(UploadsDB(), A)
    codes = [_ticket(client).status_code for _ in range(21)]
    assert codes == [200] * 20 + [429]


# ---- POST /uploads: the ticket ----------------------------------------------------------


def test_ticket_signs_a_server_chosen_path_in_the_callers_folder() -> None:
    db = UploadsDB()
    resp = _ticket(client_for(db, A))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"uploadId", "signedUrl"}
    uuid.UUID(body["uploadId"])
    assert db.ops("sign_upload") == [f"{A}/{body['uploadId']}"]
    assert f"/{BUCKET}/{A}/{body['uploadId']}?" in body["signedUrl"]


@pytest.mark.parametrize(
    "extra",
    [
        {"contentType": "image/gif"},
        {"contentType": "application/pdf"},
        {"contentType": "image/svg+xml"},  # scriptable: never accepted as an "image"
        {"sizeBytes": MAX_BYTES + 1},
        {"sizeBytes": 0},
        {"userId": B},
        {"path": f"{B}/mine-now"},
    ],
    ids=["gif", "pdf", "svg", "too-big", "empty", "body-user", "body-path"],
)
def test_ticket_refuses_bad_requests_before_signing_anything(
    extra: dict[str, Any],
) -> None:
    db = UploadsDB()
    assert _ticket(client_for(db, A), **extra).status_code == 422
    assert db.ops("sign_upload") == []


# ---- POST /uploads/{id}/complete ---------------------------------------------------------


def test_complete_records_what_storage_holds_and_returns_a_download_url() -> None:
    db = UploadsDB()
    upload_id = str(uuid.uuid4())
    db.put(A, upload_id, size=3000, mimetype="image/png")
    resp = _complete(db, A, upload_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["id"], body["sizeBytes"], body["contentType"]) == (
        upload_id,
        3000,
        "image/png",
    )
    assert body["downloadUrl"].startswith(f"https://cdn.example/{A}/{upload_id}?")
    assert db.tables["uploads"][0]["user_id"] == A
    assert db.rpc_calls[-1] == (
        "record_upload",
        {
            "p_user_id": A,
            "p_upload_id": upload_id,
            "p_max_bytes": MAX_BYTES,
            "p_allowed_types": list(ALLOWED_TYPES),
        },
    )


def test_complete_is_idempotent() -> None:
    db = UploadsDB()
    upload_id = str(uuid.uuid4())
    db.put(A, upload_id)
    first, again = (
        _complete(db, A, upload_id).json(),
        _complete(db, A, upload_id).json(),
    )
    assert first["id"] == again["id"]
    assert len(db.tables["uploads"]) == 1


def test_complete_before_the_bytes_land_is_a_404() -> None:
    assert _complete(UploadsDB(), A, str(uuid.uuid4())).status_code == 404


def test_cannot_claim_another_users_upload() -> None:
    db = UploadsDB()
    upload_id = str(uuid.uuid4())
    path = db.put(A, upload_id)
    assert _complete(db, B, upload_id).status_code == 404
    assert db.tables.get("uploads", []) == []
    assert path in db.files


@pytest.mark.parametrize(
    ("size", "mimetype"),
    [(MAX_BYTES + 1, "image/jpeg"), (2048, "image/gif"), (2048, "text/html")],
)
def test_complete_rejects_and_removes_what_should_never_have_landed(
    size: int, mimetype: str
) -> None:
    db = UploadsDB()
    upload_id = str(uuid.uuid4())
    path = db.put(A, upload_id, size=size, mimetype=mimetype)
    assert _complete(db, A, upload_id).status_code == 422
    assert path not in db.files
    assert db.tables.get("uploads", []) == []


def test_complete_needs_a_uuid() -> None:
    db = UploadsDB()
    assert _complete(db, A, "not-a-uuid").status_code == 422
    assert _complete(db, A, f"..%2F{B}").status_code in (404, 422)
    assert not [c for c in db.rpc_calls if c[0] == "record_upload"]


# ---- GET + DELETE ---------------------------------------------------------------------------


def _two_users_uploads(db: UploadsDB) -> tuple[str, str]:
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    db.put(A, mine)
    db.put(B, theirs)
    _complete(db, A, mine)
    _complete(db, B, theirs)
    db.storage.calls.clear()
    return mine, theirs


def test_list_returns_only_the_callers_uploads() -> None:
    db = UploadsDB()
    mine, _ = _two_users_uploads(db)
    body = client_for(db, A).get("/api/v1/uploads").json()
    assert [i["id"] for i in body["items"]] == [mine]
    assert db.ops("sign") == [f"{A}/{mine}"]


def test_delete_removes_the_object_and_the_row() -> None:
    db = UploadsDB()
    mine, theirs = _two_users_uploads(db)
    assert client_for(db, A).delete(f"/api/v1/uploads/{mine}").status_code == 204
    assert f"{A}/{mine}" not in db.files
    assert [r["id"] for r in db.tables["uploads"]] == [theirs]


def test_cannot_delete_another_users_upload() -> None:
    db = UploadsDB()
    _, theirs = _two_users_uploads(db)
    assert client_for(db, A).delete(f"/api/v1/uploads/{theirs}").status_code == 404
    assert f"{B}/{theirs}" in db.files
    assert db.ops("remove") == []
    assert len(db.tables["uploads"]) == 2


# ---- account deletion + data export ----------------------------------------------------------


def _delete_account(db: UploadsDB, user: str) -> Any:
    return client_for(db, user).request(
        "DELETE", "/api/v1/me", json={"confirm": "DELETE"}
    )


def test_account_deletion_empties_the_callers_folder_first() -> None:
    db = UploadsDB()
    for i in range(uploads_service.LIST_PAGE * 2 + 5):  # more than one list() page
        db.put(A, f"{i:04d}")
    db.put(A, "never-completed")
    db.put(B, "keep-me")
    assert _delete_account(db, A).status_code == 204
    assert list(db.files) == [f"{B}/keep-me"]
    assert db.auth.admin.deleted == [A]


def test_account_survives_when_its_files_cannot_be_removed() -> None:
    db = UploadsDB()
    db.put(A, "photo")
    db.storage.error = RuntimeError("storage down")
    assert _delete_account(db, A).status_code == 500
    assert db.auth.admin.deleted == [], "the account went, its files stayed"


def test_delete_user_files_stops_when_storage_removes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = UploadsDB()
    db.put(A, "stuck")
    monkeypatch.setattr(FakeBucket, "remove", lambda self, paths: [])
    with pytest.raises(RuntimeError, match="did not remove"):
        uploads_service.delete_user_files(db, A)


def test_export_lists_the_callers_files_with_download_links() -> None:
    db = UploadsDB()
    mine, theirs = _two_users_uploads(db)
    body = client_for(db, A).get("/api/v1/me/export").json()
    rows = body["tables"]["uploads"]
    assert [r["id"] for r in rows] == [mine]
    ttl = uploads_service.EXPORT_URL_TTL
    assert rows[0]["download_url"].startswith(
        f"https://cdn.example/{A}/{mine}?ttl={ttl}"
    )
    assert theirs not in str(body)


# ---- one set of limits ------------------------------------------------------------------------


def _migration() -> str:
    found = sorted((ROOT / "supabase" / "migrations").glob("*_uploads.sql"))
    assert found, "the uploads migration is missing"
    return found[-1].read_text(encoding="utf-8")


def test_bucket_limits_match_the_api() -> None:
    sql = _migration()
    m = re.search(
        r"values \(\s*'uploads', 'uploads', false, (\d+),\s*array\[([^\]]*)\]", sql
    )
    assert m, "bucket insert not found in the uploads migration"
    assert int(m.group(1)) == MAX_BYTES
    assert tuple(re.findall(r"'([^']+)'", m.group(2))) == ALLOWED_TYPES


def test_request_model_accepts_exactly_the_allowed_types() -> None:
    assert typing.get_args(uploads_router.ContentType) == ALLOWED_TYPES
