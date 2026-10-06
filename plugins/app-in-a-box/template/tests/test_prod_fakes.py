"""A filter-honouring fake Supabase client shared by the tests/test_prod_* suites.

Every filter really filters, so a handler that forgets `.eq("user_id", ...)` touches
other users' rows and the test fails. `rpc()` dispatches to Python stand-ins for the
Postgres functions (the SQL itself is exercised by test_prod_migrations.py's
integration test against a real Postgres). `storage` is an in-memory Storage whose
`list()` returns only the folder asked for (files, plus sub-folders with `id: None`, as
the real API does), so a path built from the wrong id misses.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

import pytest

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db

PROD_VARS = (
    "CRON_SECRET",
    "EXPO_ACCESS_TOKEN",
    "CORS_ORIGINS",
    "LOG_FORMAT",
    "APP_VERSION",
    "RAILWAY_GIT_COMMIT_SHA",
    "GIT_SHA",
    "SENTRY_RELEASE",
)


def clear_prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROD_VARS:
        monkeypatch.delenv(name, raising=False)


def wire_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")


class FakeAPIError(Exception):
    """Shaped like postgrest.exceptions.APIError: `.code` is the SQLSTATE."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _split(expr: str) -> list[str]:
    """Split on top-level commas (not inside parentheses or double quotes)."""
    parts, depth, quoted, cur = [], 0, False, ""
    i = 0
    while i < len(expr):
        c = expr[i]
        if c == "\\" and quoted:
            cur += expr[i : i + 2]
            i += 2
            continue
        if c == '"':
            quoted = not quoted
        elif not quoted and c in "()":
            depth += 1 if c == "(" else -1
        if c == "," and depth == 0 and not quoted:
            parts.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    return [*parts, cur]


def _parse_or(expr: str) -> list[Any]:
    """-> a list of terms; a term is (col, op, value) or ("and", [terms])."""
    terms: list[Any] = []
    for part in _split(expr):
        if part.startswith("and(") and part.endswith(")"):
            terms.append(("and", _parse_or(part[4:-1])))
            continue
        col, op, value = part.split(".", 2)
        if value.startswith('"'):
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        terms.append((col, op, value))
    return terms


def _term(row: dict[str, Any], term: Any) -> bool:
    if term[0] == "and":
        return all(_term(row, t) for t in term[1])
    col, op, value = term
    have = row.get(col)
    if have is None:
        return False
    a, b = str(have), str(value)
    return {"eq": a == b, "gt": a > b, "lt": a < b}[op]


def _any_term(row: dict[str, Any], terms: Any) -> bool:
    return any(_term(row, t) for t in terms)


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, db: FakeDB, table: str) -> None:
        self.db = db
        self.table = table
        self.op = "select"
        self.payload: Any = None
        self.filters: list[tuple[str, str, Any]] = []
        self._orders: list[tuple[str, bool]] = []  # like SQL: first key wins, rest break ties
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None

    # builders
    def select(self, *_cols: Any) -> FakeQuery:
        self.op = "select"
        return self

    def insert(self, rows: Any) -> FakeQuery:
        self.op, self.payload = "insert", rows
        return self

    def update(self, patch: dict[str, Any]) -> FakeQuery:
        self.op, self.payload = "update", patch
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str = "id") -> FakeQuery:
        self.op, self.payload = "upsert", (row, on_conflict)
        return self

    def delete(self) -> FakeQuery:
        self.op = "delete"
        return self

    # filters
    def eq(self, col: str, val: Any) -> FakeQuery:
        self.filters.append(("eq", col, val))
        return self

    def in_(self, col: str, vals: Any) -> FakeQuery:
        self.filters.append(("in", col, list(vals)))
        return self

    def lt(self, col: str, val: Any) -> FakeQuery:
        self.filters.append(("lt", col, val))
        return self

    def gt(self, col: str, val: Any) -> FakeQuery:
        self.filters.append(("gt", col, val))
        return self

    def or_(self, expr: str) -> FakeQuery:
        """PostgREST's `or=(...)`: `a.gt."x",and(a.eq."x",b.gt."y")` (what keyset() sends)."""
        self.filters.append(("or", "", _parse_or(expr)))
        return self

    def is_(self, col: str, val: str) -> FakeQuery:
        self.filters.append(("is", col, val))
        return self

    def order(self, col: str, desc: bool = False) -> FakeQuery:
        self._orders.append((col, desc))
        return self

    def limit(self, n: int) -> FakeQuery:
        self._limit = n
        return self

    def range(self, start: int, end: int) -> FakeQuery:
        self._range = (start, end)
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for kind, col, val in self.filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
            if kind == "lt" and not (row.get(col) is not None and str(row[col]) < str(val)):
                return False
            if kind == "is" and val == "null" and row.get(col) is not None:
                return False
            if kind == "gt" and not (row.get(col) is not None and str(row[col]) > str(val)):
                return False
            if kind == "or" and not _any_term(row, val):
                return False
        return True

    def execute(self) -> Result:
        rows = self.db.tables.setdefault(self.table, [])
        self.db.calls.append((self.table, self.op, list(self.filters)))
        if self.op == "insert":
            new = self.payload if isinstance(self.payload, list) else [self.payload]
            key = self.db.unique.get(self.table)
            for r in new:
                if key and any(all(e.get(k) == r.get(k) for k in key) for e in rows):
                    raise FakeAPIError("23505", "duplicate key")
            rows.extend(dict(r) for r in new)
            return Result([dict(r) for r in new])
        if self.op == "upsert":
            row, conflict = self.payload
            existing = next((r for r in rows if r.get(conflict) == row.get(conflict)), None)
            if existing:
                existing.update(row)
                return Result([existing])
            rows.append(dict(row))
            return Result([dict(row)])
        matched = [r for r in rows if self._match(r)]
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if r not in matched]
            return Result(matched)
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return Result(matched)
        for col, desc in reversed(self._orders):  # stable sorts, minor key first
            matched.sort(key=lambda r: str(r.get(col)), reverse=desc)
        if self._range:
            matched = matched[self._range[0] : self._range[1] + 1]
        if self._limit is not None:
            matched = matched[: self._limit]
        return Result([dict(r) for r in matched])


class _Rpc:
    def __init__(self, fn: Callable[[], Any]) -> None:
        self._fn = fn

    def execute(self) -> Result:
        return Result(self._fn())


class FakeAdmin:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.error: Exception | None = None

    def delete_user(self, user_id: str, should_soft_delete: bool = False) -> None:
        if self.error:
            raise self.error
        self.deleted.append(user_id)


class FakeAuth:
    def __init__(self) -> None:
        self.admin = FakeAdmin()


class FakeBucket:
    """One Storage bucket: `db.storage.from_("x")`. Objects are `{path: metadata}`."""

    def __init__(self, storage: FakeStorage, bucket: str) -> None:
        self.storage = storage
        self.bucket = bucket
        self.objects = storage.objects.setdefault(bucket, {})

    def create_signed_upload_url(self, path: str) -> dict[str, str]:
        self.storage.calls.append((self.bucket, "sign_upload", path))
        base = "https://example.supabase.co/storage/v1/object/upload/sign"
        url = f"{base}/{self.bucket}/{path}?token=t"
        return {"signed_url": url, "signedUrl": url, "token": "t", "path": path}

    def create_signed_urls(self, paths: list[str], expires_in: int) -> list[dict[str, Any]]:
        self.storage.calls.extend((self.bucket, "sign", p) for p in paths)
        return [
            {"path": p, "signedURL": f"https://cdn.example/{p}?ttl={expires_in}", "error": None}
            for p in paths
        ]

    def list(
        self, path: str | None = None, options: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """The folder's direct children, sorted by name like the real API: files with
        their metadata, and each sub-folder once as `{"name": ..., "id": None}`."""
        if self.storage.error:
            raise self.storage.error
        opts = options or {}
        prefix = f"{path}/" if path else ""
        children: dict[str, dict[str, Any]] = {}
        for key in self.objects:
            if not key.startswith(prefix):
                continue
            head, sep, _ = key[len(prefix) :].partition("/")
            if sep:
                children[head] = {"name": head, "id": None, "metadata": None}
            else:
                children[head] = {"name": head, "id": head, "metadata": self.objects[key]}
        start = int(opts.get("offset", 0))
        page = [children[n] for n in sorted(children)]
        return page[start : start + int(opts.get("limit", 100))]

    def remove(self, paths: list[str]) -> list[dict[str, Any]]:
        if self.storage.error:
            raise self.storage.error
        self.storage.calls.extend((self.bucket, "remove", p) for p in paths)
        return [{"name": p} for p in paths if self.objects.pop(p, None) is not None]


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, dict[str, Any]]] = {}  # bucket -> path -> metadata
        self.calls: list[tuple[str, str, str]] = []  # (bucket, op, path)
        self.error: Exception | None = None

    def from_(self, bucket: str) -> FakeBucket:
        return FakeBucket(self, bucket)


class FakeDB:
    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = tables or {}
        self.calls: list[tuple[str, str, list[tuple[str, str, Any]]]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.unique: dict[str, tuple[str, ...]] = {"job_runs": ("job", "run_key")}
        self.counters: dict[str, int] = {}
        self.rpc_error: Exception | None = None
        self.auth = FakeAuth()
        self.storage = FakeStorage()
        self._ids = itertools.count(1)

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def rpc(self, fn: str, params: dict[str, Any]) -> _Rpc:
        self.rpc_calls.append((fn, dict(params)))
        if self.rpc_error:
            err = self.rpc_error

            def boom() -> Any:
                raise err

            return _Rpc(boom)
        return _Rpc(lambda: getattr(self, f"_rpc_{fn}")(**params))

    # Python stand-ins for the SQL functions in supabase/migrations
    def _rpc_rate_limit_hit(self, p_key: str, p_window_seconds: int) -> int:
        self.counters[p_key] = self.counters.get(p_key, 0) + 1
        return self.counters[p_key]

    def _rpc_idempotency_claim(
        self,
        p_user_id: str,
        p_key: str,
        p_fingerprint: str,
        p_stale_seconds: int,
        p_ttl_seconds: int,
    ) -> list[dict[str, Any]]:
        """No clock here: expiry and stale takeover are covered by the SQL integration test."""
        rows = self.tables.setdefault("idempotency_keys", [])
        row = next((r for r in rows if r["user_id"] == p_user_id and r["key"] == p_key), None)
        if row is None:
            rows.append({"user_id": p_user_id, "key": p_key, "fingerprint": p_fingerprint,
                         "response_status": None, "response_body": None,
                         "response_content_type": None})  # fmt: skip
            return [{"claimed": True, "stored_fingerprint": p_fingerprint, "stored_status": None,
                     "stored_body": None, "stored_content_type": None}]  # fmt: skip
        return [
            {
                "claimed": False,
                "stored_fingerprint": row["fingerprint"],
                "stored_status": row.get("response_status"),
                "stored_body": row.get("response_body"),
                "stored_content_type": row.get("response_content_type"),
            }
        ]

    def _rpc_register_push_token(
        self, p_user_id: str, p_token: str, p_platform: str | None, p_max_tokens: int
    ) -> None:
        rows = self.tables.setdefault("push_tokens", [])
        seq = next(self._ids)
        existing = next((r for r in rows if r["token"] == p_token), None)
        if existing:
            existing.update(user_id=p_user_id, last_seen=seq)
        else:
            rows.append(
                {"user_id": p_user_id, "token": p_token, "platform": p_platform, "last_seen": seq}
            )
        mine = sorted((r for r in rows if r["user_id"] == p_user_id), key=lambda r: -r["last_seen"])
        drop = mine[p_max_tokens:]
        self.tables["push_tokens"] = [r for r in rows if r not in drop]


def client_for(db: FakeDB, user_id: str | None = "u1", app: Any = None) -> Any:
    from fastapi.testclient import TestClient

    from backend.main import create_app

    app = app or create_app()
    if user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


# The fake is itself a guard: prove its filters bite, or the suites above prove nothing.
def test_fake_eq_filters_rows() -> None:
    db = FakeDB({"t": [{"user_id": "a"}, {"user_id": "b"}]})
    assert db.table("t").select("*").eq("user_id", "b").execute().data == [{"user_id": "b"}]


def test_fake_delete_only_removes_matched_rows() -> None:
    db = FakeDB({"t": [{"user_id": "a", "k": 1}, {"user_id": "b", "k": 1}]})
    db.table("t").delete().eq("user_id", "a").in_("k", [1]).execute()
    assert db.tables["t"] == [{"user_id": "b", "k": 1}]


def test_fake_enforces_job_runs_primary_key() -> None:
    db = FakeDB()
    db.table("job_runs").insert({"job": "j", "run_key": "k"}).execute()
    with pytest.raises(FakeAPIError):
        db.table("job_runs").insert({"job": "j", "run_key": "k"}).execute()


def test_fake_storage_lists_only_the_folder_asked_for() -> None:
    bucket = FakeDB().storage.from_("files")
    bucket.objects.update({"a/1": {"size": 1}, "b/2": {}, "a/sub/3": {}, "a/sub/4": {}})
    sub = {"name": "sub", "id": None, "metadata": None}  # a folder, listed once
    assert bucket.list("a") == [{"name": "1", "id": "1", "metadata": {"size": 1}}, sub]
    assert bucket.list("a", {"limit": 1, "offset": 1}) == [sub]
    assert [e["name"] for e in bucket.list("a/sub")] == ["3", "4"]
    assert bucket.remove(["b/2", "a/missing"]) == [{"name": "b/2"}]
    assert set(bucket.objects) == {"a/1", "a/sub/3", "a/sub/4"}


def test_fake_order_breaks_ties_with_later_keys() -> None:
    db = FakeDB({"t": [{"a": 1, "b": "y"}, {"a": 0, "b": "z"}, {"a": 1, "b": "x"}]})
    rows = db.table("t").select("*").order("a").order("b").execute().data
    assert [(r["a"], r["b"]) for r in rows] == [(0, "z"), (1, "x"), (1, "y")]
