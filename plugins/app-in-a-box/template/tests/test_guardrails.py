"""Guardrail packs (scripts/check_guardrails.py): the repo is clean, every rule FAILS on a
planted violation with its own message, and a pack that is off costs nothing (the same
plant passes until the pack is turned on in privacy/data-map.yaml).

Each test copies the repo into tmp_path and plants one thing, so the real files are
never touched.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_guardrails.py"
_spec = importlib.util.spec_from_file_location("check_guardrails", SCRIPT)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

_SKIP = shutil.ignore_patterns("node_modules", ".venv", ".git", "__pycache__", ".pytest_cache")


@pytest.fixture
def app(tmp_path: Path) -> Path:
    dst = tmp_path / "app"
    for name in ("mobile", "backend", "supabase", "scripts", "privacy"):
        if (ROOT / name).is_dir():
            shutil.copytree(ROOT / name, dst / name, ignore=_SKIP)
    return dst


def packs(app: Path, *on: str, **extra: object) -> None:
    """Turn packs on in the data map (keeping the rest of it) and sync lib/packs.ts."""
    path = app / guard.DATA_MAP
    data = yaml.safe_load(path.read_text()) if path.is_file() else {}
    data = data if isinstance(data, dict) else {}
    data["packs"] = list(on)
    data.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    assert guard.main(["--root", str(app), "--write"]) == 0


def edit(app: Path, rel: str, old: str, new: str) -> None:
    p = app / rel
    text = p.read_text()
    assert old in text, f"{old!r} not in {rel}"
    p.write_text(text.replace(old, new, 1))


def append(app: Path, rel: str, text: str) -> None:
    p = app / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text((p.read_text() if p.exists() else "") + text)


def problems(app: Path) -> str:
    return "\n".join(guard.check(app))


def migration(app: Path, sql: str, name: str = "20990101000000_planted.sql") -> None:
    append(app, f"supabase/migrations/{name}", sql)


# ---- the real repo -----------------------------------------------------------------


def test_repo_is_clean() -> None:
    assert guard.check(ROOT) == []


def test_every_pack_has_checks_or_widens_the_lints() -> None:
    for pack in guard.PACKS:
        assert guard.CHECKS[pack] or pack in guard.PII, pack


def test_cli_fails_with_the_message(app: Path) -> None:
    append(
        app,
        "backend/routers/planted.py",
        "import logging\nlogger = logging.getLogger(__name__)\n\n\ndef f(user):\n    logger.info('x %s', user.email)\n",
    )
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(app)], capture_output=True, text=True
    )
    assert out.returncode == 1
    assert "check_guardrails: [baseline] backend/routers/planted.py:6: `email` logged" in out.stdout


# ---- which packs are on ------------------------------------------------------------


def test_no_data_map_means_baseline_only(app: Path) -> None:
    (app / guard.DATA_MAP).unlink(missing_ok=True)
    assert guard.enabled_packs(guard.load_data_map(app)) == ({"baseline"}, [])


def test_packs_line_is_read_without_pyyaml() -> None:
    assert guard._packs_line("packs: [location, 'minors']\ntables: {}\n") == ["location", "minors"]
    assert guard._packs_line("packs:\n  - health\n  - ugc\n") == ["health", "ugc"]
    assert guard._packs_line("tables: {}\n") == []


def test_unknown_pack_is_caught(app: Path) -> None:
    append(app, guard.DATA_MAP, "packs: [locaton]\n")
    assert "unknown pack 'locaton'" in problems(app)


def test_stale_packs_ts_is_caught(app: Path) -> None:
    append(app, guard.DATA_MAP, "packs: [health]\n")
    assert "mobile/lib/packs.ts does not match" in problems(app)


# ---- baseline ----------------------------------------------------------------------


def test_analytics_helper_with_an_email_is_caught(app: Path) -> None:
    edit(
        app,
        guard.ANALYTICS_TS,
        "  updatePrompted: () =>",
        '  invited: (p: { email: string }) => capture("invited", p),\n  updatePrompted: () =>',
    )
    assert "analytics payload key `email` looks like an email address" in problems(app)


@pytest.mark.parametrize(
    "args, needle",
    [
        (
            '"home", { lat: pos.coords.latitude }',
            "`lat` passed to analytics looks like a precise location",
        ),
        ('"home", { note: draft }', "`note` passed to analytics looks like free text"),
        (
            '"home", { who: user.displayName }',
            "`displayName` passed to analytics looks like a person's name",
        ),
    ],
)
def test_analytics_call_with_personal_data_is_caught(app: Path, args: str, needle: str) -> None:
    edit(
        app,
        "mobile/app/(app)/index.tsx",
        "export default function",
        f"export function Planted() {{\n  analytics.screenViewed({args});\n}}\n\nexport default function",
    )
    assert needle in problems(app)


def test_string_contents_and_comments_are_not_flagged(app: Path) -> None:
    edit(
        app,
        "mobile/app/(app)/index.tsx",
        "export default function",
        'export function Planted() {\n  // the email screen\n  analytics.screenViewed("email_settings");\n}\n\nexport default function',
    )
    assert problems(app) == ""


def test_waiver_needs_the_right_pack_and_a_reason(app: Path) -> None:
    line = '  analytics.screenViewed("home", { full_name: "x" });'
    edit(
        app,
        "mobile/app/(app)/index.tsx",
        "export default function",
        f"export function Planted() {{\n{line} // guardrail-ok(health): nope\n}}\n\nexport default function",
    )
    assert "`full_name` passed to analytics" in problems(app)
    edit(
        app,
        "mobile/app/(app)/index.tsx",
        "guardrail-ok(health): nope",
        "guardrail-ok(baseline): the field's NAME, a fixed enum",
    )
    assert problems(app) == ""


def test_posthog_called_directly_is_caught(app: Path) -> None:
    edit(
        app,
        "mobile/app/(app)/index.tsx",
        "export default function",
        'export function Planted() {\n  posthog?.capture("x", {});\n}\n\nexport default function',
    )
    assert "posthog.capture() called directly" in problems(app)


def test_personal_data_in_a_log_call_is_caught(app: Path) -> None:
    append(
        app,
        "backend/routers/planted.py",
        "import logging\nlogger = logging.getLogger(__name__)\n\n\ndef f(body, user):\n    logger.warning(f'bad payload {body}')\n    logger.info('ok %s', user.id)\n",
    )
    out = problems(app)
    assert "planted.py:6: `body` logged; it looks like free text" in out
    assert ":7:" not in out


def test_a_removed_scrubber_is_caught(app: Path) -> None:
    edit(app, "mobile/lib/monitoring.ts", "beforeSend: scrubSentryEvent,", "")
    edit(app, guard.ANALYTICS_TS, "scrubProps(props)", "props")
    out = problems(app)
    assert "Sentry.init has no beforeSend: scrubSentryEvent" in out
    assert "capture() no longer runs scrubProps()" in out


# ---- a pack that is off costs nothing ----------------------------------------------


@pytest.mark.parametrize(
    "pack, key, needle",
    [
        ("health", "heart_rate", "looks like a health value"),
        ("financial", "balance", "looks like a financial value"),
        ("biometric", "faceprint", "looks like a biometric value"),
        ("minors", "school", "looks like a child's age or school"),
    ],
)
def test_pack_widens_the_payload_lint_only_when_on(
    app: Path, pack: str, key: str, needle: str
) -> None:
    edit(
        app,
        guard.ANALYTICS_TS,
        "  updatePrompted: () =>",
        f'  planted: (p: {{ {key}: number }}) => capture("planted", p),\n  updatePrompted: () =>',
    )
    assert problems(app) == ""  # off: nothing runs, nothing flagged
    packs(app, pack)
    assert needle in problems(app)


def test_location_plant_passes_until_the_pack_is_on(app: Path) -> None:
    migration(
        app, "create table public.check_ins (id uuid primary key, latitude double precision);\n"
    )
    assert problems(app) == ""
    packs(app, "location")
    assert "table `check_ins` stores location (latitude)" in problems(app)


# ---- location ----------------------------------------------------------------------


def _background(app: Path) -> None:
    cfg = json.loads((app / "mobile/app.json").read_text())
    cfg["expo"]["ios"]["infoPlist"] = {"UIBackgroundModes": ["location"]}
    (app / "mobile/app.json").write_text(json.dumps(cfg))


def test_background_location_needs_a_reason_and_a_purpose_string(app: Path) -> None:
    packs(app, "location")
    _background(app)
    out = problems(app)
    assert "background location is requested (ios.infoPlist.UIBackgroundModes)" in out
    assert "no purpose string tells the user why" in out
    packs(
        app,
        "location",
        permissions={"location_background": "so your family sees you got home safely"},
    )
    cfg = json.loads((app / "mobile/app.json").read_text())
    cfg["expo"]["plugins"].append(
        [
            "expo-location",
            {
                "locationAlwaysAndWhenInUsePermission": "Shares your arrival home with the family you chose."
            },
        ]
    )
    (app / "mobile/app.json").write_text(json.dumps(cfg))
    assert problems(app) == ""


def test_a_raw_position_read_is_caught_and_who_can_see_me_required(app: Path) -> None:
    packs(app, "location")
    append(
        app,
        "mobile/lib/where.ts",
        "import * as Location from 'expo-location';\nexport async function here() {\n  return (await Location.getCurrentPositionAsync()).coords;\n}\n",
    )
    out = problems(app)
    assert "mobile/lib/where.ts:3: reads a position without coarsen()" in out
    assert "no screen under mobile/app/ renders <WhoCanSeeMe>" in out
    edit(app, "mobile/lib/where.ts", "return (await", "return coarsen((await")
    edit(app, "mobile/lib/where.ts", ").coords;", ").coords);")
    edit(
        app,
        "mobile/app/(app)/index.tsx",
        "export default function",
        'export const Planted = () => <WhoCanSeeMe audience="Only you" />;\n\nexport default function',
    )
    assert problems(app) == ""


def test_a_location_table_needs_a_ttl_the_prune_cron_enforces(app: Path) -> None:
    packs(app, "location")
    migration(
        app, "create table public.trips (id uuid primary key, route geography(linestring));\n"
    )
    assert "table `trips` stores location (route)" in problems(app)
    edit(
        app,
        guard.JOBS,
        '"rate_limits": ("window_start", timedelta(days=1)),',
        '"rate_limits": ("window_start", timedelta(days=1)),\n    "trips": ("created_at", timedelta(days=30)),',
    )
    assert problems(app) == ""


def test_data_map_location_category_counts_too(app: Path) -> None:
    packs(
        app,
        "location",
        tables={
            "visits": {
                "owner": "user",
                "columns": {"spot": {"category": "location", "retention": "P30D"}},
            }
        },
    )
    assert "table `visits` stores location (spot)" in problems(app)


# ---- minors ------------------------------------------------------------------------


def test_minors_guards(app: Path) -> None:
    packs(app, "minors")
    edit(app, "mobile/app/(auth)/sign-in.tsx", "<AgeGate status={age} onDone={setAge} />", "{null}")
    edit(
        app,
        guard.ANALYTICS_TS,
        "  if (suppressed) return;\n  try {\n    posthog?.capture",
        "  try {\n    posthog?.capture",
    )
    append(
        app,
        "mobile/package.json",
        json.dumps({"dependencies": {"react-native-google-mobile-ads": "1.0.0"}}),
    )
    migration(
        app,
        "create table public.profiles_ext (id uuid primary key, is_public boolean not null default true);\ncreate table public.messages (id uuid primary key);\n",
    )
    out = problems(app)
    assert "no screen under mobile/app/ renders <AgeGate>" in out
    assert "capture() no longer checks the age gate's suppression" in out
    assert "depends on `react-native-google-mobile-ads`" in out
    assert "a visibility column defaults to public" in out
    assert "table `messages` looks like user-to-user messaging" in out


def test_messaging_can_be_kept_with_a_recorded_reason(app: Path) -> None:
    packs(app, "minors")
    migration(
        app,
        "-- guardrail-ok(minors): parents message their own child's coach only\ncreate table public.messages (id uuid primary key);\n",
    )
    assert "messaging" not in problems(app)


# ---- financial, biometric, ugc -----------------------------------------------------


def test_float_money_is_caught(app: Path) -> None:
    packs(app, "financial")
    migration(
        app, "create table public.pots (\n  id uuid primary key,\n  amount double precision\n);\n"
    )
    assert "money column `amount` is double precision" in problems(app)


def test_stored_biometric_template_is_caught(app: Path) -> None:
    packs(app, "biometric")
    migration(app, "alter table public.profiles add column face_embedding bytea;\n")
    assert "`profiles.face_embedding` looks like a stored biometric template" in problems(app)


def test_ugc_needs_report_block_and_a_queue(app: Path) -> None:
    packs(app, "ugc")
    migration(app, "create table public.posts (id uuid primary key, body text not null);\n")
    out = problems(app)
    for needle in (
        "no reports table",
        "no blocks table",
        "path says `report`",
        "path says `block`",
    ):
        assert needle in out, needle
    migration(
        app,
        "create table public.content_reports (id uuid primary key, post_id uuid, status text not null default 'open');\n"
        "create table public.user_blocks (blocker uuid, blocked uuid);\n",
        "20990101000100_moderation.sql",
    )
    append(
        app,
        "backend/routers/planted.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n\n\n@router.post('/posts/{post_id}/report')\ndef report(post_id: str) -> None: ...\n\n\n@router.post('/users/{user_id}/block')\ndef block(user_id: str) -> None: ...\n",
    )
    assert problems(app) == ""


def test_reports_table_without_a_status_is_caught(app: Path) -> None:
    packs(app, "ugc")
    migration(
        app,
        "create table public.comments (id uuid primary key);\ncreate table public.reports (id uuid primary key);\n",
    )
    assert "the reports table has no `status`" in problems(app)


# ---- the runtime scrubber agrees with the lint -------------------------------------


def test_mobile_scrubber_covers_every_lint_category() -> None:
    ts = (ROOT / "mobile/lib/privacy.ts").read_text()
    body = ts[ts.index("export const SENSITIVE_KEY") : ts.index('].join("|")')]
    scrub = re.compile("|".join(re.findall(r'^\s*"([^"]+)",?$', body, re.M)))
    every = set(guard.PACKS)
    samples = [
        "email",
        "phone",
        "first_name",
        "street",
        "lat",
        "longitude",
        "message",
        "note",
        "password",
        "dob",
        "heart_rate",
        "glucose",
        "balance",
        "iban",
        "fingerprint",
        "face_embedding",
        "age",
    ]
    for s in samples:
        assert guard.classify(s, every), s
        assert scrub.search(s), f"lib/privacy.ts SENSITIVE_KEY does not strip `{s}`"
    for s in ["screen", "route", "duration_ms", "error_code", "page"]:
        assert not guard.classify(s, every) and not scrub.search(s), s
    # a measure of the value is not the value (both sides skip it; MEASURE is mirrored)
    for s in ["query_length", "note_count", "has_email"]:
        assert not guard.classify(s, every), s
    measure_ts = re.search(r"const MEASURE = /(.+)/;", ts)
    assert measure_ts and measure_ts.group(1) == guard.MEASURE.pattern


# ---- Semgrep is wired, pinned and tested -------------------------------------------


def test_semgrep_runs_pinned_with_its_own_tests() -> None:
    req = (ROOT / "requirements-semgrep.txt").read_text()
    assert re.search(r"^semgrep==\d+\.\d+\.\d+$", req, re.M), "pin semgrep exactly"
    sec = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())
    runs = "\n".join(str(s.get("run") or "") for s in sec["jobs"]["semgrep"]["steps"])
    assert "--require-hashes -r requirements-semgrep.lock" in runs
    assert "semgrep --test" in runs and ".semgrep/backend.py" in runs
    assert re.search(r"semgrep scan --config \.semgrep/backend\.yml --error .*backend", runs)


def test_every_semgrep_rule_has_a_firing_test_case() -> None:
    rules = yaml.safe_load((ROOT / ".semgrep/backend.yml").read_text())["rules"]
    cases = (ROOT / ".semgrep/backend.py").read_text()
    for rule in rules:
        assert f"# ruleid: {rule['id']}" in cases, f"{rule['id']} has no `# ruleid:` case"
