"""FE <-> BE wire contract: Pydantic models vs the `*Wire` interfaces in mobile/lib/api.ts,
compared field by field in BOTH directions, for responses AND request bodies.

There is no codegen; the two sides are mirrored by hand, and mobile ships on a release
train, so a build from weeks ago is always reading today's JSON. `apiFetch<T>()` is a
cast, not a check: TypeScript cannot see drift. In a real app the backend nested a field
the client read at the top level; eight fields drifted unnoticed for months and users
saw "Set weight" instead of their prescribed load.

Request bodies rot just as quietly, and worse: rename `ProfileUpdate.display_name` and
a client PATCH `{"displayName": ...}` still returns 200, having stored nothing. So every
request model (a) is paired here and (b) has `extra="forbid"`, which turns an unknown
field into a 422 instead of a silent drop. Without (b), "field the app sends that the
API doesn't know" has no observable effect, and a guard for it has no teeth.

Per (model, interface) pair in RESPONSE_PAIRS / REQUEST_PAIRS:
  1. names: the model's camelCase aliases == the interface's properties
  2. nullability: `X | None` on the model <=> `| null` in TS
  3. presence: a model field with no default is always sent (response) or required
     (request), so TS may not mark it `?:`
  4. kind: str->string, int/float->number, bool->boolean, Literal->"a" | "b",
     list->[], nested model->its Wire
And: every response_model the app serves and every body model it accepts must be paired
(an unlisted endpoint is an unguarded endpoint). Each check has a negative control.

Adding an endpoint: add its `XWire` interface + adapter to mobile/lib/api.ts and the
pair below, in the same PR.
"""

from __future__ import annotations

import json
import re
import types
import typing
from pathlib import Path
from typing import Any, Literal

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend.main import create_app
from backend.routers.export import DataExport
from backend.routers.me import AccountDeletion, Profile, ProfileUpdate, Wire
from backend.routers.push import PushTokenIn, PushTokenRef

ROOT = Path(__file__).resolve().parents[1]
API_TS = ROOT / "mobile" / "lib" / "api.ts"

# (Pydantic response model, TS interface in mobile/lib/api.ts)
RESPONSE_PAIRS: list[tuple[type[BaseModel], str]] = [
    (Profile, "ProfileWire"),
    (DataExport, "DataExportWire"),
]
# (Pydantic request-body model, TS interface the app builds the body from)
REQUEST_PAIRS: list[tuple[type[BaseModel], str]] = [
    (ProfileUpdate, "ProfilePatchWire"),
    (AccountDeletion, "AccountDeletionWire"),
    (PushTokenIn, "PushTokenWire"),
    (PushTokenRef, "PushTokenRefWire"),
]
WIRE_PAIRS = RESPONSE_PAIRS + REQUEST_PAIRS
PY_TO_TS = {str: "string", int: "number", float: "number", bool: "boolean"}
Direction = Literal["response", "request"]


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
    if typing.get_origin(py) is Literal:
        return " | ".join(json.dumps(v) for v in typing.get_args(py))
    return f"<unchecked {py!r}>"


def _ts_base(expr: str) -> tuple[str, bool]:
    parts = [p.strip() for p in expr.split("|")]
    nullable = "null" in parts
    rest = [p for p in parts if p not in ("null", "undefined")]
    base = " | ".join(rest)
    base = re.sub(r"^Array<(.+)>$", r"\1[]", base)
    return base, nullable


_WORDS: dict[Direction, dict[str, str]] = {
    "response": {
        "model_only": "sent by the API, missing from the TS interface",
        "ts_only": "read by the app, never sent by the API",
        "required_optional": "always sent, but TS marks it optional `?:`",
        "null_hidden": "API may send null but TS says never",
        "null_phantom": "TS allows null the API never sends",
    },
    "request": {
        "model_only": "accepted by the API, missing from the TS type",
        "ts_only": "sent by the app, rejected by the API (extra=forbid -> 422)",
        "required_optional": "required by the API (422 without it), but TS marks it optional `?:`",
        "null_hidden": "API accepts null but TS says never",
        "null_phantom": "TS allows null the API rejects",
    },
}


def compare(
    model: type[BaseModel],
    iface: dict[str, tuple[str, bool]],
    pairs: dict[type, str],
    direction: Direction = "response",
) -> list[str]:
    words = _WORDS[direction]
    problems = []
    fields = {}
    for name, f in model.model_fields.items():
        alias = f.serialization_alias or f.alias or name
        fields[alias] = f
    for alias in sorted(set(fields) - set(iface)):
        problems.append(f"{model.__name__}.{alias}: {words['model_only']}")
    for prop in sorted(set(iface) - set(fields)):
        problems.append(f"{model.__name__}.{prop}: {words['ts_only']}")
    for alias in sorted(set(fields) & set(iface)):
        f = fields[alias]
        expr, optional = iface[alias]
        inner, py_null = _unwrap(f.annotation)
        ts_type, ts_null = _ts_base(expr)
        if py_null != ts_null:
            side = words["null_hidden"] if py_null else words["null_phantom"]
            problems.append(f"{model.__name__}.{alias}: nullability drift ({side})")
        if f.is_required() and optional:
            problems.append(f"{model.__name__}.{alias}: {words['required_optional']}")
        want = _ts_kind(inner, pairs)
        if not want.startswith("<unchecked") and want != ts_type:
            problems.append(f"{model.__name__}.{alias}: type drift (API {want}, TS {ts_type})")
    return problems


def unforbidden(models: list[type[BaseModel]]) -> list[str]:
    """Request models that would silently DROP an unknown field instead of 422-ing."""
    return [m.__name__ for m in models if m.model_config.get("extra") != "forbid"]


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


def unpaired_body_models(app: Any, listed: set[type]) -> list[str]:
    """Request-body models with no *Wire pair. Two body parameters make FastAPI
    synthesize a `Body_<op>` model, which is also unlisted, so that fails too: one
    Pydantic model per body, mirrored by name, is the contract."""
    missing = set()
    for route in _api_routes(app.routes):
        if route.body_field is None:
            continue
        model = _unwrap(route.body_field.field_info.annotation)[0]
        where = f"({route.path} {'/'.join(sorted(route.methods or ()))})"
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            missing.add(f"<non-model body {model!r}> {where}")
        elif model not in listed:
            missing.add(f"{model.__module__}.{model.__name__} {where}")
    return sorted(missing)


# ---- the real contract -----------------------------------------------------------------

PAIRS = dict(WIRE_PAIRS)


@pytest.mark.parametrize(("model", "interface"), RESPONSE_PAIRS, ids=[i for _, i in RESPONSE_PAIRS])
def test_wire_mirrors_mobile_types(model: type[BaseModel], interface: str) -> None:
    iface = ts_interface(API_TS.read_text(encoding="utf-8"), interface)
    problems = compare(model, iface, PAIRS, "response")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(("model", "interface"), REQUEST_PAIRS, ids=[i for _, i in REQUEST_PAIRS])
def test_request_bodies_mirror_mobile_types(model: type[BaseModel], interface: str) -> None:
    iface = ts_interface(API_TS.read_text(encoding="utf-8"), interface)
    problems = compare(model, iface, PAIRS, "request")
    assert not problems, "\n".join(problems)


def test_request_models_reject_unknown_fields() -> None:
    loose = unforbidden([m for m, _ in REQUEST_PAIRS])
    assert not loose, (
        f"request models without extra='forbid': {loose}. A renamed or body-supplied "
        "field must be a 422, not a silent drop (subclass WireIn)."
    )


def test_every_served_response_model_is_paired() -> None:
    missing = unpaired_response_models(create_app(), set(PAIRS))
    assert not missing, (
        f"response models with no *Wire pair (unguarded endpoints): {missing}. Add an "
        "interface + adapter in mobile/lib/api.ts and a RESPONSE_PAIRS entry."
    )


def test_every_accepted_body_model_is_paired() -> None:
    missing = unpaired_body_models(create_app(), set(PAIRS))
    assert not missing, (
        f"request-body models with no *Wire pair (unguarded endpoints): {missing}. Add an "
        "interface in mobile/lib/api.ts, build the body from it, and add a REQUEST_PAIRS entry."
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
    ("edit", "needle"),
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


class _SampleIn(Wire):
    """A request body with the shapes the real ones use: a literal, an optional
    nullable, an enum-literal-or-null."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    confirm: Literal["DELETE"]
    display_name: str | None = Field(default=None, max_length=80)
    platform: Literal["ios", "android"] | None = None


SAMPLE_IN_TS = """
export interface SampleInWire {
  confirm: "DELETE";
  displayName?: string | null;
  platform?: "ios" | "android" | null;
}
"""


def _drift_in(ts: str) -> list[str]:
    return compare(_SampleIn, ts_interface(ts, "SampleInWire"), {}, "request")


def test_baseline_request_sample_is_clean() -> None:
    assert _drift_in(SAMPLE_IN_TS) == []


@pytest.mark.parametrize(
    ("edit", "needle"),
    [
        (("displayName?: string | null;", ""), "missing from the TS type"),
        (("confirm: \"DELETE\";", "confirm: \"DELETE\";\n  userId: string;"), "rejected by the API"),
        (("confirm: \"DELETE\"", "confirm?: \"DELETE\""), "marks it optional"),
        (("confirm: \"DELETE\"", "confirm: \"DELETE\" | \"REMOVE\""), "type drift"),
        (("\"ios\" | \"android\" | null", "\"ios\" | null"), "type drift"),
        (("displayName?: string | null", "displayName?: string"), "accepts null but TS says never"),
        (("confirm: \"DELETE\"", "confirm: \"DELETE\" | null"), "TS allows null the API rejects"),
    ],
    ids=[
        "removed",
        "client-sends-owner-id",
        "required-marked-optional",
        "literal-widened",
        "literal-narrowed",
        "null-hidden",
        "null-phantom",
    ],
)
def test_each_request_drift_is_caught(edit: tuple[str, str], needle: str) -> None:
    problems = _drift_in(SAMPLE_IN_TS.replace(*edit))
    assert any(needle in p for p in problems), problems


def test_a_renamed_request_field_is_caught_against_the_real_client() -> None:
    """The exact drift this guard exists for: `ProfileUpdate.display_name` -> `name`.
    Without the pairing, a client PATCH {"displayName": ...} returns 200 and stores
    nothing (with extra="ignore") or 422s every client in the wild (with "forbid")."""

    class Renamed(Wire):
        model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
        name: str | None = Field(default=None, max_length=80)
        onboarded: bool | None = None

    iface = ts_interface(API_TS.read_text(encoding="utf-8"), "ProfilePatchWire")
    problems = compare(Renamed, iface, PAIRS, "request")
    assert any(p.startswith("Renamed.name:") and "missing from the TS type" in p for p in problems)
    assert any(p.startswith("Renamed.displayName:") and "rejected by the API" in p for p in problems)


def test_a_loose_request_model_is_caught() -> None:
    class Loose(Wire):
        token: str

    assert unforbidden([Loose, _SampleIn]) == ["Loose"]


def test_missing_interface_fails_loudly() -> None:
    with pytest.raises(LookupError):
        ts_interface(SAMPLE_TS, "NopeWire")


def test_unpaired_endpoint_is_caught() -> None:
    missing = unpaired_response_models(create_app(), set())
    assert any("Profile" in m for m in missing), missing


def test_unpaired_body_model_is_caught() -> None:
    missing = unpaired_body_models(create_app(), set())
    assert any("ProfileUpdate" in m and "PATCH" in m for m in missing), missing
    assert any("AccountDeletion" in m and "DELETE" in m for m in missing), missing
