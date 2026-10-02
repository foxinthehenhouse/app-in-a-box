"""Every service-key query is scoped to the caller (static guard, no DB needed).

The backend talks to Supabase with the SERVICE key, so row-level security never
applies: a query is exactly as user-scoped as the filters it chains, and no more.
A real app shipped two cross-user leaks from reads that filtered only by some other id.
The ownership tests in tests/test_me.py catch a missing filter for the endpoints
they cover; this guard covers every `.table(...)` chain in backend/, including the
ones nobody has written a test for yet.

A chain starting at `.table("...")` must also contain `.eq("user_id", ...)` or
`.eq("id", <something>.id)` (a table keyed by the auth user id, like `profiles`).
A chain that genuinely can't carry that filter goes in ALLOWLIST as
"<path>:<function>" with a written reason. A stale entry fails too, so the list can
only shrink honestly. Each rule has a negative control.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

ALLOWLIST: dict[str, str] = {
    "backend/routers/me.py:update_me": (
        "Upsert keyed on the primary key `id`, where the row's `id` is overwritten with "
        "the verified token's user.id on the line above (`{**patch, 'id': user.id}`). "
        "An upsert can't take .eq(); tests/test_me.py::test_patch_cannot_write_someone_elses_row "
        "proves a body-supplied id is ignored."
    ),    "backend/main.py:_db_ping": (
        "Deep health check touches the singleton keep_alive row (id=1): system table, no user data, service-role only."
    ),
    "backend/services/jobs_service.py:claim_run": (
        "job_runs is the system ledger of cron runs (one row per job+period); it holds no user data and is only reached behind the cron secret."
    ),
    "backend/services/jobs_service.py:release_run": (
        "Deletes this cron run's own unfinished job_runs claim after a crash so the retry can run; system ledger, no user data, behind the cron secret."
    ),
    "backend/services/jobs_service.py:finish_run": (
        "Updates the job_runs ledger row this cron run claimed; system table with no user data, reached only behind the cron secret."
    ),
    "backend/services/jobs_service.py:prune_rate_limits": (
        "Deletes expired rate_limits buckets for every caller by design; a global housekeeping job behind the cron secret, reads nothing back."
    ),
    "backend/services/jobs_service.py:weekly_digest": (
        "The weekly digest is cross-user by design (iterates onboarded profiles to push each their own digest); only runs behind the cron secret, returns counts only."
    ),
    "backend/services/push_service.py:send_to_user": (
        "Inserts push_tickets rows stamped with the caller-supplied user_id whose tokens were just read with .eq('user_id', user_id); an insert has no filter to add."
    ),
    "backend/services/push_service.py:check_receipts": (
        "Receipt polling is a global cron job over all pending push_tickets (Expo receipts are keyed by ticket id, not user); behind the cron secret, returns counts only."
    ),
}


def _chain(node: ast.AST) -> list[tuple[str, list[ast.expr]]]:
    """Method calls of a fluent chain, innermost first."""
    calls: list[tuple[str, list[ast.expr]]] = []
    cur = node
    while True:
        if isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute):
            calls.append((cur.func.attr, list(cur.args)))
            cur = cur.func.value
        elif isinstance(cur, ast.Attribute):
            cur = cur.value
        else:
            break
    return calls[::-1]


def _str(e: ast.expr) -> str | None:
    return e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None


def _is_user_id(e: ast.expr) -> bool:
    """`user.id`, `current_user.id`, `user_id`: a value that came from the token."""
    if isinstance(e, ast.Attribute) and e.attr == "id":
        return isinstance(e.value, ast.Name) and e.value.id in {"user", "current_user", "caller"}
    return isinstance(e, ast.Name) and e.id in {"user_id", "uid"}


def _scoped(chain: list[tuple[str, list[ast.expr]]]) -> bool:
    for name, args in chain:
        if name != "eq" or len(args) < 2:
            continue
        col = _str(args[0])
        if col == "user_id" or (col == "id" and _is_user_id(args[1])):
            return True
    return False


def _owners(tree: ast.AST) -> dict[int, str]:
    owner: dict[int, str] = {}

    def visit(node: ast.AST, fn: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            owner[id(child)] = name
            visit(child, name)

    visit(tree, "<module>")
    return owner


def find_unscoped(source: str, rel_path: str) -> list[tuple[str, int, str]]:
    """(key, line, table) for each `.table(...)` chain without a user-id filter."""
    tree = ast.parse(source)
    owner = _owners(tree)
    # A chain's top is the outermost node: not the receiver of a further `.attr` and
    # not the `func` of a call (`...execute().data` tops out at `.data`).
    inner = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    inner |= {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    found = []
    nodes = (n for n in ast.walk(tree) if isinstance(n, (ast.Call, ast.Attribute)))
    for top in (n for n in nodes if id(n) not in inner):
        chain = _chain(top)
        idx = next((i for i, (name, _) in enumerate(chain) if name == "table"), None)
        if idx is None or not chain[idx][1]:
            continue
        table = _str(chain[idx][1][0]) or "<dynamic>"
        if not _scoped(chain[idx:]):
            found.append((f"{rel_path}:{owner.get(id(top), '<module>')}", top.lineno, table))
    return found


def scan(root: Path) -> list[tuple[str, int, str]]:
    out = []
    for path in sorted((root / "backend").rglob("*.py")):
        out += find_unscoped(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix())
    return out


def test_the_scan_sees_queries() -> None:
    """Vacuity: if the detector stopped finding chains, 'no offenders' means nothing."""
    total = sum(src.count(".table(") for src in (p.read_text() for p in BACKEND.rglob("*.py")))
    assert total >= 2


def test_every_query_is_scoped_to_the_caller() -> None:
    offenders = [r for r in scan(ROOT) if r[0] not in ALLOWLIST]
    assert not offenders, (
        "Unscoped service-key queries (the service key bypasses RLS; add "
        '.eq("user_id", user.id), or allowlist with a reason):\n'
        + "\n".join(f"  {k} (line {line}) table={t}" for k, line, t in offenders)
    )


def test_allowlist_entries_are_live_and_justified() -> None:
    live = {r[0] for r in scan(ROOT)}
    stale = sorted(k for k in ALLOWLIST if k not in live)
    assert not stale, f"ALLOWLIST entries that no longer match an unscoped query: {stale}"
    assert all(len(r) > 40 for r in ALLOWLIST.values())


# ---- negative controls ---------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        'def f(db, pid):\n    db.table("posts").select("*").eq("id", pid).execute()',
        'def f(db):\n    db.table("posts").select("*").limit(5).execute()',
        'def f(db, u):\n    db.table("posts").select("*").neq("user_id", u.id).execute()',
        'def f(db, body):\n    db.table("posts").update({"x": 1}).eq("id", body["id"]).execute()',
        'def f(db):\n    db.table("posts").delete().execute()',
        'def f(db, item):\n    db.table("posts").select("*").eq("id", item.id).execute()',
    ],
    ids=["other-id", "no-filter", "neq", "body-id", "delete-all", "non-user-attr-id"],
)
def test_detector_flags_unscoped(snippet: str) -> None:
    assert [k for k, _, _ in find_unscoped(snippet, "x.py")] == ["x.py:f"]


@pytest.mark.parametrize(
    "snippet",
    [
        'def f(db, user):\n    db.table("posts").select("*").eq("user_id", user.id).execute()',
        'def f(db, user):\n    db.table("profiles").select("*").eq("id", user.id).limit(1).execute()',
        'def f(db, user, pid):\n    db.table("posts").update({}).eq("id", pid).eq("user_id", user.id).execute()',
        'def f(db, user_id):\n    db.table("posts").delete().eq("user_id", user_id).execute()',
    ],
)
def test_detector_passes_scoped(snippet: str) -> None:
    assert find_unscoped(snippet, "x.py") == []


def test_removing_the_real_filter_is_caught() -> None:
    """The exact edit selftest plants: drop `.eq("id", user.id)` from routers/me.py."""
    src = (BACKEND / "routers" / "me.py").read_text()
    assert '.eq("id", user.id)' in src
    broken = src.replace('.eq("id", user.id)', "")
    assert "backend/routers/me.py:read_me" in {
        k for k, _, _ in find_unscoped(broken, "backend/routers/me.py")
    }
