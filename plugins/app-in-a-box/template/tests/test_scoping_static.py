"""Every service-key query is scoped to the caller (static guard, no DB needed).

The backend talks to Supabase with the SERVICE key, so row-level security never
applies: a query is exactly as user-scoped as the filters it chains, and no more.
A real app shipped two cross-user leaks from reads that filtered only by some other id.
The ownership tests in tests/test_me.py catch a missing filter for the endpoints
they cover; this guard covers every `.table(...)` chain in backend/, including the
ones nobody has written a test for yet.

A chain starting at `.table("...")` must contain `.eq("user_id", <token id>)` or
`.eq("id", <token id>)` (a table keyed by the auth user id, like `profiles`), where
<token id> PROVABLY came from the verified token, not from the request:
  - `user.id` where `user: CurrentUser` is a parameter of the enclosing function
    (any name; it is the annotation that proves the origin), or a local assigned
    from that (`user_id = user.id`);
  - a bare `user_id` / `uid` PARAMETER of a plain function (a service helper the
    router calls with `user.id`) -- but never in a route handler, where a bare
    parameter is a query string value, and never with a `Query(...)`/`Body(...)`/...
    default.
`.eq("user_id", body.user_id)`, `.eq("user_id", body["userId"])` and
`.eq("user_id", uid)` with `uid` a query parameter all look scoped and are not: they
let the caller choose whose rows to touch. The column name alone proved nothing.

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
    ),
    "backend/main.py:_db_ping": (
        "Deep health check touches the singleton keep_alive row (id=1): system table, no user data, service-role only."
    ),
    "backend/services/jobs_service.py:claim_run": (
        "job_runs is the system ledger of cron runs (one row per job+period); it holds no user data and is only reached behind the cron secret. The delete reclaims a stale unfinished claim of the same (job, run_key)."
    ),
    "backend/services/jobs_service.py:_insert_claim": (
        "Inserts the (job, run_key) row into the job_runs system ledger for claim_run(); no user data, and an insert has no filter to add. Behind the cron secret."
    ),
    "backend/services/jobs_service.py:release_run": (
        "Deletes this cron run's own unfinished job_runs claim after a crash so the retry can run; system ledger, no user data, behind the cron secret."
    ),
    "backend/services/jobs_service.py:finish_run": (
        "Updates the job_runs ledger row this cron run claimed; system table with no user data, reached only behind the cron secret."
    ),
    "backend/services/jobs_service.py:prune_rate_limits": (
        "Deletes expired rate_limits buckets and idempotency_keys past their TTL for every caller by design; a global housekeeping job behind the cron secret, reads nothing back."
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

Fn = ast.FunctionDef | ast.AsyncFunctionDef
_ID_NAMES = {"user_id", "uid"}
_TOKEN_TYPE = "CurrentUser"
# A parameter with one of these as default/annotation is request data, not the token.
_REQUEST_MARKERS = {"Query", "Body", "Path", "Header", "Cookie", "Form", "File"}
_ROUTE_METHODS = {
    "get", "post", "put", "patch", "delete", "head", "options", "trace", "api_route", "route",
}  # fmt: skip


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


def _is_route_handler(fn: Fn) -> bool:
    for d in fn.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        if isinstance(target, ast.Attribute) and target.attr in _ROUTE_METHODS:
            return True
    return False


def _annotation_names(ann: ast.expr | None) -> set[str]:
    """Every name an annotation mentions: `X`, `m.X`, `"X"`, `Annotated[X, Dep()]`."""
    if ann is None:
        return set()
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        return {ann.value.split(".")[-1]}
    names = set()
    for node in ast.walk(ann):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _params(fn: Fn) -> list[ast.arg]:
    return fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs


def _default_of(fn: Fn, name: str) -> ast.expr | None:
    positional = fn.args.posonlyargs + fn.args.args
    defaults = [None] * (len(positional) - len(fn.args.defaults)) + list(fn.args.defaults)
    for a, d in zip(positional, defaults, strict=True):
        if a.arg == name:
            return d
    for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults, strict=True):
        if a.arg == name:
            return d
    return None


def _is_marker(e: ast.expr | None) -> bool:
    if not isinstance(e, ast.Call):
        return False
    target = e.func
    name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
    return name in _REQUEST_MARKERS


def _token_params(fn: Fn) -> set[str]:
    return {a.arg for a in _params(fn) if _TOKEN_TYPE in _annotation_names(a.annotation)}


def _is_user_id(e: ast.expr, fn: Fn | None) -> bool:
    """A value that PROVABLY came from the verified token (see the module docstring)."""
    if fn is None:
        return False
    if isinstance(e, ast.Attribute) and e.attr == "id" and isinstance(e.value, ast.Name):
        return e.value.id in _token_params(fn)
    if isinstance(e, ast.Name) and e.id in _ID_NAMES:
        params = {a.arg: a for a in _params(fn)}
        if e.id in params:
            if _is_route_handler(fn):
                return False  # a bare handler parameter is a query-string value
            ann = params[e.id].annotation
            marker_in_annotation = any(
                _is_marker(n) for n in ast.walk(ann) if isinstance(n, ast.Call)
            ) if ann is not None else False
            return not (_is_marker(_default_of(fn, e.id)) or marker_in_annotation)
        for node in ast.walk(fn):  # a local: `user_id = user.id`
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == e.id
            ):
                return _is_user_id(node.value, fn)
    return False


def _scoped(chain: list[tuple[str, list[ast.expr]]], fn: Fn | None) -> bool:
    for name, args in chain:
        if name != "eq" or len(args) < 2:
            continue
        if _str(args[0]) in ("user_id", "id") and _is_user_id(args[1], fn):
            return True
    return False


def _owners(tree: ast.AST) -> dict[int, Fn | None]:
    """node id -> the innermost function that contains it (None at module level)."""
    owner: dict[int, Fn | None] = {}

    def visit(node: ast.AST, fn: Fn | None) -> None:
        for child in ast.iter_child_nodes(node):
            here = child if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else fn
            owner[id(child)] = here
            visit(child, here)

    visit(tree, None)
    return owner


def find_unscoped(source: str, rel_path: str) -> list[tuple[str, int, str]]:
    """(key, line, table) for each `.table(...)` chain without a token-scoped filter."""
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
        fn = owner.get(id(top))
        if not _scoped(chain[idx:], fn):
            found.append((f"{rel_path}:{fn.name if fn else '<module>'}", top.lineno, table))
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
        '.eq("user_id", user.id) with `user: CurrentUser`, or allowlist with a reason):\n'
        + "\n".join(f"  {k} (line {line}) table={t}" for k, line, t in offenders)
    )


def test_allowlist_entries_are_live_and_justified() -> None:
    live = {r[0] for r in scan(ROOT)}
    stale = sorted(k for k in ALLOWLIST if k not in live)
    assert not stale, f"ALLOWLIST entries that no longer match an unscoped query: {stale}"
    assert all(len(r) > 40 for r in ALLOWLIST.values())


# ---- negative controls ---------------------------------------------------------------

_HANDLER = '@router.get("/x")\n'


@pytest.mark.parametrize(
    "snippet",
    [
        'def f(db, pid):\n    db.table("posts").select("*").eq("id", pid).execute()',
        'def f(db):\n    db.table("posts").select("*").limit(5).execute()',
        'def f(db, u: CurrentUser):\n    db.table("posts").select("*").neq("user_id", u.id).execute()',
        'def f(db, body):\n    db.table("posts").update({"x": 1}).eq("id", body["id"]).execute()',
        'def f(db):\n    db.table("posts").delete().execute()',
        'def f(db, item):\n    db.table("posts").select("*").eq("id", item.id).execute()',
        # the column is right, the VALUE is the caller's choice:
        'def f(db, body):\n    db.table("posts").select("*").eq("user_id", body.user_id).execute()',
        'def f(db, body):\n    db.table("posts").select("*").eq("user_id", body["userId"]).execute()',
        _HANDLER + 'def f(db, uid: str):\n    db.table("posts").select("*").eq("user_id", uid).execute()',
        'def f(db, uid: str = Query()):\n    db.table("posts").select("*").eq("user_id", uid).execute()',
        'def f(db, user_id: Annotated[str, Query()]):\n    db.table("posts").select("*").eq("user_id", user_id).execute()',
        _HANDLER + 'def f(db, user: ProfileIn):\n    db.table("posts").select("*").eq("user_id", user.id).execute()',
        'def f(db, user):\n    db.table("posts").select("*").eq("user_id", user.id).execute()',
        _HANDLER + 'def f(db, body, user: CurrentUser):\n    user_id = body.user_id\n    db.table("posts").select("*").eq("user_id", user_id).execute()',
        'db.table("posts").select("*").eq("user_id", user_id).execute()',
    ],
    ids=[
        "other-id",
        "no-filter",
        "neq",
        "body-id",
        "delete-all",
        "non-user-attr-id",
        "body-attr-user-id",
        "body-subscript-user-id",
        "query-param-in-handler",
        "query-marker-default",
        "query-marker-annotated",
        "body-model-dot-id",
        "untyped-user-dot-id",
        "local-from-body",
        "module-level",
    ],
)
def test_detector_flags_unscoped(snippet: str) -> None:
    keys = [k for k, _, _ in find_unscoped(snippet, "x.py")]
    assert keys in (["x.py:f"], ["x.py:<module>"]), keys


@pytest.mark.parametrize(
    "snippet",
    [
        'def f(db, user: CurrentUser):\n    db.table("posts").select("*").eq("user_id", user.id).execute()',
        'def f(db, user: CurrentUser):\n    db.table("profiles").select("*").eq("id", user.id).limit(1).execute()',
        'def f(db, user: CurrentUser, pid):\n    db.table("posts").update({}).eq("id", pid).eq("user_id", user.id).execute()',
        _HANDLER + 'def f(db, user: CurrentUser = Depends(get_current_user)):\n    db.table("posts").select("*").eq("user_id", user.id).execute()',
        _HANDLER + 'def f(db, caller: Annotated[CurrentUser, Depends(get_current_user)]):\n    db.table("posts").select("*").eq("user_id", caller.id).execute()',
        _HANDLER + 'def f(db, user: CurrentUser):\n    user_id = user.id\n    db.table("posts").select("*").eq("user_id", user_id).execute()',
        'def f(db, user_id: str):\n    db.table("posts").delete().eq("user_id", user_id).execute()',
        'def f(db, user_id, start, end):\n    return db.table("profiles").select("*").eq("id", user_id).range(start, end).execute().data',
    ],
    ids=[
        "user-dot-id",
        "profiles-id",
        "two-filters",
        "handler-depends",
        "handler-annotated",
        "handler-local",
        "service-param",
        "service-param-untyped",
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


def test_swapping_the_token_for_the_body_is_caught() -> None:
    """A subtler plant: keep the filter, feed it the body's id instead of the token's."""
    src = (BACKEND / "routers" / "push.py").read_text()
    assert '.eq("user_id", user.id)' in src
    broken = src.replace('.eq("user_id", user.id)', '.eq("user_id", body.user_id)')
    assert "backend/routers/push.py:unregister_push_token" in {
        k for k, _, _ in find_unscoped(broken, "backend/routers/push.py")
    }
