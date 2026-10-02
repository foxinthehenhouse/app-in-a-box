"""FE <-> BE wire contract: Pydantic response models vs the `*Wire` interfaces in
mobile/lib/api.ts, compared field by field in BOTH directions.

There is no codegen; the two sides are mirrored by hand, and mobile ships on a release
train, so a build from weeks ago is always reading today's JSON. `apiFetch<T>()` is a
cast, not a check: TypeScript cannot see drift. In a real app the backend nested a field
the client read at the top level; eight fields drifted unnoticed for months and users
saw "Set weight" instead of their prescribed load.

Per (model, interface) pair in WIRE_PAIRS:
  1. names: the model's camelCase aliases == the interface's properties
  2. nullability: `X | None` on the model <=> `| null` in TS
  3. presence: a model field with no default is always sent, so TS may not mark it `?:`
  4. kind: str->string, int/float->number, bool->boolean, list->[], nested model->its Wire
And: every response_model the app serves must be in WIRE_PAIRS (an unlisted endpoint
is an unguarded endpoint). Each check has a negative control.

Adding an endpoint: add its `XWire` interface + adapter to mobile/lib/api.ts and the
pair below, in the same PR.
"""

from __future__ import annotations

import re
import types
import typing
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from backend.main import create_app
from backend.routers.export import DataExport
from backend.routers.me import Profile

ROOT = Path(__file__).resolve().parents[1]
API_TS = ROOT / "mobile" / "lib" / "api.ts"

# (Pydantic response model, TS interface in mobile/lib/api.ts)
WIRE_PAIRS: list[tuple[type[BaseModel], str]] = [
    (Profile, "ProfileWire"),
    (DataExport, "DataExportWire"),
]
PY_TO_TS = {str: "string", int: "number", float: "number", bool: "boolean"}


# ---- TypeScript side ----------------------------------------------------------------


def ts_interface(src: str, name: str) -> dict[str, tuple[str, bool]]:
    """{prop: (type expression, optional?)} for `export interface <name> { ... }`."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    m = re.search(rf"\binterface\s+{re.escape(name)}\s*(?:extends\s+[^{{]+)?\{{", src)
    if not m:
        raise LookupError(f"interface {name} not found in mobile/lib/api.ts")
    depth, i = 1, m.end()
    while depth and i < len(src):
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        i += 1
    body = src[m.end() : i - 1]
    props: dict[str, tuple[str, bool]] = {}
    for member in re.split(r";\s*|\n", body):
        member = member.strip().rstrip(",")
        if not member:
            continue
        mm = re.match(r"^(?:readonly\s+)?([A-Za-z_$][\w$]*)(\??)\s*:\s*(.+)$", member)
        if not mm:
            raise ValueError(f"{name}: cannot parse member {member!r}")
        props[mm.group(1)] = (mm.group(3).strip(), mm.group(2) == "?")
    return props


# ---- Python side --------------------------------------------------------------------


def _unwrap(annotation: Any) -> tuple[Any, bool]:
    """(inner type, nullable?) for `X | None` / Optional[X]."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        nullable = len(args) != len(typing.get_args(annotation))
        return (args[0] if len(args) == 1 else annotation), nullable
    return annotation, False


def _ts_kind(py: Any, pairs: dict[type, str]) -> str:
    if py in PY_TO_TS:
        return PY_TO_TS[py]
    if isinstance(py, type) and issubclass(py, BaseModel):
        return pairs.get(py, f"<unpaired model {py.__name__}>")
    if typing.get_origin(py) is list:
        (inner,) = typing.get_args(py) or (Any,)
        return _ts_kind(_unwrap(inner)[0], pairs) + "[]"
    return f"<unchecked {py!r}>"


def _ts_base(expr: str) -> tuple[str, bool]:
    parts = [p.strip() for p in expr.split("|")]
    nullable = "null" in parts
    rest = [p for p in parts if p not in ("null", "undefined")]
    base = " | ".join(rest)
    base = re.sub(r"^Array<(.+)>$", r"\1[]", base)
    return base, nullable


def compare(
    model: type[BaseModel], iface: dict[str, tuple[str, bool]], pairs: dict[type, str]
) -> list[str]:
    problems = []
    fields = {}
    for name, f in model.model_fields.items():
        alias = f.serialization_alias or f.alias or name
        fields[alias] = f
    for alias in sorted(set(fields) - set(iface)):
        problems.append(f"{model.__name__}.{alias}: sent by the API, missing from the TS interface")
    for prop in sorted(set(iface) - set(fields)):
        problems.append(f"{model.__name__}.{prop}: read by the app, never sent by the API")
    for alias in sorted(set(fields) & set(iface)):
        f = fields[alias]
        expr, optional = iface[alias]
        inner, py_null = _unwrap(f.annotation)
        ts_type, ts_null = _ts_base(expr)
        if py_null != ts_null:
            side = (
                "API may send null but TS says never"
                if py_null
                else "TS allows null the API never sends"
            )
            problems.append(f"{model.__name__}.{alias}: nullability drift ({side})")
        if f.is_required() and optional:
            problems.append(f"{model.__name__}.{alias}: always sent, but TS marks it optional `?:`")
        want = _ts_kind(inner, pairs)
        if not want.startswith("<unchecked") and want != ts_type:
            problems.append(f"{model.__name__}.{alias}: type drift (API {want}, TS {ts_type})")
    return problems


def _api_routes(routes: Any) -> list[APIRoute]:
    """Every APIRoute, including ones FastAPI wraps for include_router (0.14x+ keeps
    included routers as lazy `_IncludedRouter` objects rather than flattening them)."""
    out: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            out.append(route)
        elif getattr(route, "original_router", None) is not None:
            out += _api_routes(route.original_router.routes)
        elif getattr(route, "routes", None):
            out += _api_routes(route.routes)
    return out


def unpaired_response_models(app: Any, listed: set[type]) -> list[str]:
    missing = set()
    for route in _api_routes(app.routes):
        if isinstance(route, APIRoute) and isinstance(route.response_model, type):
            rm = route.response_model
            if issubclass(rm, BaseModel) and rm not in listed:
                missing.add(f"{rm.__module__}.{rm.__name__} ({route.path})")
    return sorted(missing)


# ---- the real contract -----------------------------------------------------------------

PAIRS = dict(WIRE_PAIRS)


@pytest.mark.parametrize("model, interface", WIRE_PAIRS, ids=[i for _, i in WIRE_PAIRS])
def test_wire_mirrors_mobile_types(model: type[BaseModel], interface: str) -> None:
    iface = ts_interface(API_TS.read_text(encoding="utf-8"), interface)
    problems = compare(model, iface, PAIRS)
    assert not problems, "\n".join(problems)


def test_every_served_response_model_is_paired() -> None:
    missing = unpaired_response_models(create_app(), set(PAIRS))
    assert not missing, (
        f"response models with no *Wire pair (unguarded endpoints): {missing}. Add an "
        "interface + adapter in mobile/lib/api.ts and a WIRE_PAIRS entry."
    )


# ---- negative controls -------------------------------------------------------------------


class _Sample(BaseModel):
    model_config = Profile.model_config
    user_id: str
    display_name: str | None = None
    streak_days: int = 0
    tags: list[str] = []


SAMPLE_TS = """
export interface SampleWire {
  userId: string;
  displayName: string | null;
  streakDays: number; // a comment
  tags: string[];
}
"""


def _drift(ts: str) -> list[str]:
    return compare(_Sample, ts_interface(ts, "SampleWire"), {})


def test_baseline_sample_is_clean() -> None:
    assert _drift(SAMPLE_TS) == []


@pytest.mark.parametrize(
    "edit, needle",
    [
        (("streakDays: number;", ""), "missing from the TS interface"),
        (("tags: string[];", "tags: string[];\n  mood: string;"), "never sent by the API"),
        (("displayName: string | null", "displayName: string"), "API may send null"),
        (("userId: string", "userId: string | null"), "TS allows null"),
        (("userId: string", "userId?: string"), "marks it optional"),
        (("streakDays: number", "streakDays: string"), "type drift"),
        (("tags: string[]", "tags: string"), "type drift"),
        (("userId", "user_id"), "missing from the TS interface"),
    ],
    ids=[
        "removed",
        "added-client-only",
        "null-hidden",
        "null-phantom",
        "optional",
        "kind",
        "list",
        "snake-case",
    ],
)
def test_each_drift_is_caught(edit: tuple[str, str], needle: str) -> None:
    problems = _drift(SAMPLE_TS.replace(*edit))
    assert any(needle in p for p in problems), problems


def test_missing_interface_fails_loudly() -> None:
    with pytest.raises(LookupError):
        ts_interface(SAMPLE_TS, "NopeWire")


def test_unpaired_endpoint_is_caught() -> None:
    missing = unpaired_response_models(create_app(), set())
    assert any("Profile" in m for m in missing), missing
