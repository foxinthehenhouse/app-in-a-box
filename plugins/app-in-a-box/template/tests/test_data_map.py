"""privacy/data-map.yaml stays complete, and the answers generated from it stay current.

scripts/check_data_map.py runs in CI and pre-commit. These prove it passes on this repo
and FAILS on each way the map goes wrong (a negative control per rule), that the map
agrees with the data export about whose data a table holds, and that the generators
produce what the stores expect.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from backend.routers import export as export_router
from scripts.schema_sql import all_sql, parse

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_data_map", ROOT / "scripts" / "check_data_map.py"
)
assert _spec is not None
assert _spec.loader is not None
dm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dm  # its dataclasses look themselves up here
_spec.loader.exec_module(dm)
MAP = yaml.safe_load((ROOT / "privacy" / "data-map.yaml").read_text())


def test_this_repo_map_is_complete_and_its_outputs_current() -> None:
    assert dm.check(ROOT) == []


# ---- the map agrees with the export and deletion paths ----------------------------------


def test_every_user_owned_table_is_owned_by_the_user_in_the_map() -> None:
    owned = {n for n, t in parse(all_sql(ROOT / "supabase" / "migrations")).items() if t.user_owned}
    assert owned, "the migration parser found no user-owned tables"
    wrong = sorted(n for n in owned if MAP["tables"][n]["owner"] != "user")
    assert not wrong, f"tables keyed to auth.users that the map doesn't call user data: {wrong}"


def test_every_user_table_in_the_map_is_exported() -> None:
    """The map is what the policy promises ("see and download your data"); the export
    is what keeps that promise. A user table in one and not the other is a broken promise."""
    user_tables = {
        n for n, t in MAP["tables"].items() if t["owner"] == "user" and not t.get("external")
    }
    covered = set(export_router.EXPORTERS) | set(export_router.NOT_EXPORTED)
    assert user_tables <= covered, sorted(user_tables - covered)


def test_account_retention_is_only_claimed_for_tables_deleted_with_the_account() -> None:
    tables = parse(all_sql(ROOT / "supabase" / "migrations"))
    for name, t in MAP["tables"].items():
        cols = (t.get("columns") or {}).values()
        if any(isinstance(c, dict) and c.get("retention") == "account" for c in cols):
            assert t.get("external") or tables[name].deleted_with_account, name


# ---- negative controls: each rule fails on a planted violation ---------------------------


@pytest.fixture
def app(tmp_path: Path) -> Path:
    """The parts of the repo the guard reads, copied so a plant can't touch the real ones."""
    for rel in ("privacy", "supabase/migrations"):
        shutil.copytree(ROOT / rel, tmp_path / rel)
    for rel in ("mobile/lib/analytics.ts", "mobile/app.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    assert dm.check(tmp_path) == []
    return tmp_path


def _edit_map(app: Path, edit) -> None:  # noqa: ANN001
    p = app / "privacy" / "data-map.yaml"
    m = yaml.safe_load(p.read_text())
    edit(m)
    p.write_text(yaml.safe_dump(m, sort_keys=False))


def _edit_app_json(app: Path, edit) -> None:  # noqa: ANN001
    p = app / "mobile" / "app.json"
    a = json.loads(p.read_text())
    edit(a["expo"])
    p.write_text(json.dumps(a, indent=2))


def test_a_column_missing_from_the_map_is_caught(app: Path) -> None:
    (app / "supabase" / "migrations" / "20990101000000_nickname.sql").write_text(
        "alter table public.profiles add column if not exists nickname text;\n"
    )
    assert dm.check(app) == [
        "data map: column profiles.nickname (supabase/migrations) is not in privacy/data-map.yaml"
    ]


def test_a_new_table_missing_from_the_map_is_caught(app: Path) -> None:
    (app / "supabase" / "migrations" / "20990101000000_notes.sql").write_text(
        "create table if not exists public.notes (id bigint primary key, user_id uuid not null "
        "references auth.users (id) on delete cascade, body text);\n"
    )
    assert dm.check(app) == [
        "data map: table notes (supabase/migrations) is not in privacy/data-map.yaml"
    ]


def test_a_map_column_no_migration_creates_is_caught(app: Path) -> None:
    _edit_map(app, lambda m: m["tables"]["profiles"]["columns"].update({"ghost": "none"}))
    assert (
        "data map: profiles.ghost is in privacy/data-map.yaml but no migration creates it"
        in dm.check(app)
    )


def test_an_analytics_prop_missing_from_the_map_is_caught(app: Path) -> None:
    ts = app / "mobile" / "lib" / "analytics.ts"
    ts.write_text(
        ts.read_text().replace(
            'capture("theme_changed", { preference })',
            'capture("theme_changed", { preference, previous: "light" })',
        )
    )
    assert dm.check(app) == [
        "data map: analytics prop 'theme_changed.previous' (mobile/lib/analytics.ts) is not in privacy/data-map.yaml"
    ]


def test_an_analytics_event_missing_from_the_map_is_caught(app: Path) -> None:
    ts = app / "mobile" / "lib" / "analytics.ts"
    ts.write_text(
        ts.read_text().replace(
            "export const analytics = {\n",
            'export const analytics = {\n  noteSaved: (p: { words: number }) => capture("note_saved", p),\n',
        )
    )
    assert dm.check(app) == [
        "data map: analytics event 'note_saved' (mobile/lib/analytics.ts) is not in privacy/data-map.yaml"
    ]


def test_a_permission_missing_from_the_map_is_caught(app: Path) -> None:
    _edit_app_json(
        app,
        lambda ex: ex["plugins"].append(
            [
                "expo-camera",
                {
                    "cameraPermission": "Take a photo of your receipt to log it.",
                    "microphonePermission": False,
                },
            ]
        ),
    )
    assert dm.check(app) == [
        "data map: permission 'camera' (mobile/app.json: plugin expo-camera cameraPermission) is not in privacy/data-map.yaml"
    ]


def test_a_plugins_default_permission_text_is_caught(app: Path) -> None:
    _edit_app_json(app, lambda ex: ex["plugins"].append("expo-location"))
    _edit_map(
        app,
        lambda m: m["permissions"].update(
            {"location_when_in_use": "show the parks near you on the map"}
        ),
    )
    probs = dm.check(app)
    assert any("ships the plugin's generic default text" in p for p in probs), probs


def test_a_sensitive_column_without_retention_is_caught(app: Path) -> None:
    _edit_map(app, lambda m: m["tables"]["profiles"]["columns"]["display_name"].pop("retention"))
    assert dm.check(app) == [
        "privacy/data-map.yaml: profiles.display_name is 'contact' (sensitive) but has no retention: say how long it's kept"
    ]


def test_sensitive_data_sent_to_analytics_is_caught(app: Path) -> None:
    _edit_map(
        app, lambda m: m["analytics"]["screen_viewed"]["props"].update({"screen": "location"})
    )
    probs = dm.check(app)
    assert len(probs) == 1
    assert (
        "analytics prop 'screen_viewed.screen' is 'location': sensitive data never goes to analytics"
        in probs[0]
    )


def test_a_generic_permission_purpose_is_caught(app: Path) -> None:
    _edit_map(
        app, lambda m: m["permissions"].update({"notifications": "Required for app functionality."})
    )
    probs = dm.check(app)
    assert len(probs) == 1
    assert "permission 'notifications' has a generic purpose" in probs[0]


def test_account_retention_on_a_table_that_survives_the_account_is_caught(app: Path) -> None:
    _edit_map(
        app, lambda m: m["tables"]["rate_limits"]["columns"]["key"].update({"retention": "account"})
    )
    assert (
        "data map: rate_limits.key says retention: account, but rate_limits isn't deleted with "
        "the account (no `references auth.users ... on delete cascade`)"
    ) in dm.check(app)


def test_a_stale_generated_file_is_caught(app: Path) -> None:
    _edit_map(
        app,
        lambda m: m["tables"]["profiles"]["columns"]["onboarded"].update(
            {"purpose": "show the tour once"}
        ),
    )
    assert dm.check(app) == [
        "privacy/PRIVACY_POLICY.md is stale (it no longer matches privacy/data-map.yaml): run python3 scripts/check_data_map.py --write"
    ]
    assert dm.write(app) == []
    assert dm.check(app) == []


def test_a_stale_privacy_manifest_is_caught(app: Path) -> None:
    _edit_app_json(
        app, lambda ex: ex["ios"]["privacyManifests"].update({"NSPrivacyAccessedAPITypes": []})
    )
    assert dm.check(app) == [
        "mobile/app.json expo.ios.privacyManifests is stale (it no longer matches privacy/data-map.yaml): run python3 scripts/check_data_map.py --write"
    ]


# ---- the generators ----------------------------------------------------------------------


def test_privacy_manifest_uses_apples_keys_and_values() -> None:
    pm = dm.privacy_manifest(MAP)
    assert pm["NSPrivacyTracking"] is False
    types = {d["NSPrivacyCollectedDataType"] for d in pm["NSPrivacyCollectedDataTypes"]}
    assert "NSPrivacyCollectedDataTypeEmailAddress" in types
    for d in pm["NSPrivacyCollectedDataTypes"]:
        assert set(d) == {
            "NSPrivacyCollectedDataType",
            "NSPrivacyCollectedDataTypeLinked",
            "NSPrivacyCollectedDataTypeTracking",
            "NSPrivacyCollectedDataTypePurposes",
        }
        assert all(
            p.startswith("NSPrivacyCollectedDataTypePurpose")
            for p in d["NSPrivacyCollectedDataTypePurposes"]
        )
    apis = {
        a["NSPrivacyAccessedAPIType"]: a["NSPrivacyAccessedAPITypeReasons"]
        for a in pm["NSPrivacyAccessedAPITypes"]
    }
    assert apis["NSPrivacyAccessedAPICategoryUserDefaults"] == ["CA92.1"]


def test_policy_draft_says_it_is_a_draft_and_not_legal_advice() -> None:
    text = (ROOT / "privacy" / "PRIVACY_POLICY.md").read_text()
    assert "(DRAFT)" in text
    assert "not legal advice" in text


@pytest.mark.parametrize(
    ("text", "generic"),
    [
        ("Required for app functionality.", True),
        ("Allow $(PRODUCT_NAME) to access your camera", True),
        ("This app needs access to your location", True),
        ("To improve your experience", True),
        ("camera", True),
        ("Lets you choose photos to upload.", False),
        ("send the reminders and updates you switch on in Settings", False),
        ("show the child's last check-in to their parent", False),
    ],
)
def test_generic_purposes(text: str, generic: bool) -> None:
    assert dm.is_generic(text) is generic


def test_analytics_parser_reads_inline_types_literals_and_spreads() -> None:
    src = (
        "export const analytics = {\n"
        '  a: (screen: string, props: Props = {}) => capture("a", { screen, ...props }),\n'
        '  b: (p: { ok: boolean; error_code: string | null }) => capture("b", p),\n'
        '  c: (optIn: boolean) => capture("c", { opt_in: optIn }),\n'
        '  d: () => capture("d"),\n'
        "};\n"
    )
    events, problems = dm.analytics_events(src)
    assert problems == []
    assert events == {"a": {"screen", "*"}, "b": {"ok", "error_code"}, "c": {"opt_in"}, "d": set()}


def test_props_behind_a_named_type_are_refused_not_guessed() -> None:
    src = 'export const analytics = {\n  a: (p: Payload) => capture("a", p),\n};\n'
    _, problems = dm.analytics_events(src)
    assert problems
    assert "can't read the props of analytics.a" in problems[0]
