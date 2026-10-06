"""Feature flags: the backend `flag()` helper (backend/flags.py) and the registry guard
(scripts/check_flags.py) that keeps every flag owned and dated, with negative controls."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend import flags
from backend import http as outbound
from backend.services import push_service as ps
from tests.test_prod_fakes import FakeDB

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("check_flags", ROOT / "scripts" / "check_flags.py")
assert _spec
assert _spec.loader
check_flags = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_flags)

TODAY = dt.date(2026, 10, 5)


# ---- flag() ---------------------------------------------------------------------------


def _posthog(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[dict[str, Any]]:
    """Route flags.py's PostHog call through `handler(request) -> httpx.Response`."""
    seen: list[dict[str, Any]] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "url": str(request.url),
                "json": json.loads(request.content),
                "timeout": request.extensions.get("timeout", {}).get("read"),
            }
        )
        return handler(request)

    monkeypatch.setattr(flags, "_transport", httpx.MockTransport(record))
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    return seen


def _flags_response(**flag_details: dict[str, Any]) -> Any:
    return lambda _req: httpx.Response(200, json={"flags": flag_details})


def test_every_flag_is_its_default_without_posthog() -> None:
    for name, spec in flags.FLAGS.items():
        assert flags.flag(name, "u1") == spec.default


def test_unregistered_flag_is_an_error_not_a_silent_default() -> None:
    with pytest.raises(KeyError):
        flags.flag("no-such-flag")


def test_posthog_decides_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _posthog(monkeypatch, _flags_response(**{"kill-push": {"enabled": True}}))
    assert flags.flag("kill-push", "u1") is True
    assert seen[0]["url"] == "https://us.i.posthog.com/flags/?v=2"
    assert seen[0]["json"] == {"api_key": "phc_test", "distinct_id": "u1"}
    assert seen[0]["timeout"] == flags.TIMEOUT_SECONDS


def test_a_flag_missing_from_posthog_keeps_its_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _posthog(monkeypatch, _flags_response())
    assert flags.flag("kill-push", "u1") is False


@pytest.mark.parametrize(
    "handler",
    [
        lambda _r: httpx.Response(500),
        lambda _r: httpx.Response(200, text="not json"),
        lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("slow", request=r)),
    ],
    ids=["5xx", "garbage", "timeout"],
)
def test_posthog_down_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, handler: Any
) -> None:
    _posthog(monkeypatch, handler)
    assert flags.flag("kill-push", "u1") is False


def test_a_dead_posthog_is_tried_once_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=r)

    seen = _posthog(monkeypatch, refuse)
    assert flags.flag("kill-push", "u1") is False
    assert len(seen) == 1, "a flag lookup must cost at most one timeout"


def test_an_open_circuit_falls_back_without_calling(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _posthog(monkeypatch, lambda _r: httpx.Response(503))
    for _ in range(outbound.FAILURE_THRESHOLD):
        assert flags.flag("kill-push", "u1") is False
    calls = len(seen)
    assert flags.flag("kill-push", "u1") is False
    assert len(seen) == calls, "the open circuit should skip PostHog"


def test_no_user_means_no_posthog_call(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _posthog(monkeypatch, _flags_response(**{"kill-push": {"enabled": True}}))
    assert flags.flag("kill-push") is False
    assert seen == []


def test_env_override_wins_even_over_posthog(monkeypatch: pytest.MonkeyPatch) -> None:
    _posthog(monkeypatch, _flags_response(**{"kill-push": {"enabled": False}}))
    monkeypatch.setenv("FLAG_KILL_PUSH", "1")
    assert flags.flag("kill-push", "u1") is True
    monkeypatch.setenv("FLAG_KILL_PUSH", "off")
    assert flags.flag("kill-push", "u1") is False


def test_kill_push_stops_every_send(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDB(
        {"push_tokens": [{"user_id": "u1", "token": "ExponentPushToken[" + "a" * 20 + "]"}]}
    )
    sent: list[Any] = []

    class NeverCalled:
        def send(self, messages: Any) -> Any:
            sent.append(messages)
            raise AssertionError("the kill switch is on")

    monkeypatch.setenv("FLAG_KILL_PUSH", "true")
    result = ps.send_to_user(db, "u1", "t", "b", client=NeverCalled())  # type: ignore[arg-type]
    assert result.sent == 0
    assert sent == []


# ---- the registry guard ---------------------------------------------------------------


def test_the_shipped_registries_pass() -> None:
    assert check_flags.problems(ROOT, TODAY) == []
    regs = check_flags.registries(ROOT)
    assert "backend/flags.py" in regs, "no backend registry"
    assert regs["backend/flags.py"], "registry read as empty"
    if (ROOT / "mobile" / "lib" / "flags.ts").exists():
        assert regs["mobile/lib/flags.ts"], "the mobile registry read as empty"


def test_backend_registry_reads_like_the_module() -> None:
    read = check_flags.read_backend((ROOT / "backend" / "flags.py").read_text())
    assert set(read) == set(flags.FLAGS)
    for name, spec in flags.FLAGS.items():
        assert read[name]["default"] == spec.default
        assert read[name]["owner"] == spec.owner
        assert read[name]["expires"] == spec.expires


def _app(tmp_path: Path, ts_entry: str = "", py_entry: str = "") -> Path:
    (tmp_path / "mobile" / "lib").mkdir(parents=True)
    (tmp_path / "backend").mkdir()
    (tmp_path / "mobile" / "lib" / "flags.ts").write_text(
        "export const FLAGS = {\n" + ts_entry + "} as const satisfies Record<string, FlagSpec>;\n"
    )
    (tmp_path / "backend" / "flags.py").write_text(
        "FLAGS: Final[dict[str, Flag]] = {\n" + py_entry + "}\n"
    )
    return tmp_path


GOOD_TS = """  "new-home": {
    default: false,
    owner: "@alex",
    expires: "2027-01-31",
    description: "The redesigned home screen, for a staged rollout.",
  },
"""
GOOD_PY = """    "kill-push": Flag(
        default=False, owner="@alex", expires="2027-01-31",
        description="Stops pushes.", kill_switch=True,
    ),
"""


def test_good_registries_pass(tmp_path: Path) -> None:
    root = _app(tmp_path, GOOD_TS, GOOD_PY)
    assert check_flags.problems(root, TODAY) == []
    assert set(check_flags.registries(root)["mobile/lib/flags.ts"]) == {"new-home"}


@pytest.mark.parametrize(
    ("ts", "py", "message"),
    [
        (GOOD_TS.replace('    owner: "@alex",\n', ""), "", "new-home: no owner"),
        (GOOD_TS.replace('    expires: "2027-01-31",\n', ""), "", "new-home: no expiry"),
        (GOOD_TS.replace("2027-01-31", "2099-01-01"), "", "more than a year out"),
        (GOOD_TS.replace("2027-01-31", "2027-02-30"), "", "is not a YYYY-MM-DD date"),
        (GOOD_TS.replace('"@alex"', '"alex"'), "", 'must be a "@handle"'),
        ("", GOOD_PY.replace(' owner="@alex",', ""), "kill-push: no owner"),
        ("", GOOD_PY.replace(' expires="2027-01-31",', ""), "kill-push: no expiry"),
        ("", GOOD_PY.replace("default=False", "default=True"), "default must be false"),
        ("", GOOD_PY.replace(" kill_switch=True,", ""), "not marked as a kill switch"),
        (
            GOOD_TS.replace('"new-home"', '"kill-push"').replace(
                "    default: false,\n", "    default: false,\n    killSwitch: true,\n"
            ),
            GOOD_PY.replace("kill_switch=True", "kill_switch=False"),
            "kill_switch is True in mobile/lib/flags.ts but False in backend/flags.py",
        ),
    ],
    ids=[
        "ts-no-owner",
        "ts-no-expiry",
        "ts-far-expiry",
        "ts-bad-date",
        "ts-bad-owner",
        "py-no-owner",
        "py-no-expiry",
        "py-kill-default-true",
        "py-kill-unmarked",
        "sides-disagree",
    ],
)
def test_a_broken_flag_is_caught(tmp_path: Path, ts: str, py: str, message: str) -> None:
    found = check_flags.problems(_app(tmp_path, ts, py), TODAY)
    assert any(message in p for p in found), found


def test_expired_flags_warn_and_list_but_never_fail(tmp_path: Path, capsys: Any) -> None:
    root = _app(tmp_path, GOOD_TS.replace("2027-01-31", "2026-09-01"), GOOD_PY)
    assert check_flags.problems(root, TODAY) == []
    assert check_flags.stale(root, TODAY) == [
        {
            "flag": "new-home",
            "where": "mobile/lib/flags.ts",
            "owner": "@alex",
            "expired": "2026-09-01",
            "days_over": 34,
        }
    ]
    assert check_flags.main(["--root", str(root), "--today", TODAY.isoformat()]) == 0
    assert "new-home expired 2026-09-01" in capsys.readouterr().out
    assert check_flags.main(["--root", str(root), "--today", TODAY.isoformat(), "--stale"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["flag"] == "new-home"


def test_unreadable_registry_fails_loudly(tmp_path: Path) -> None:
    root = _app(tmp_path)
    (root / "mobile" / "lib" / "flags.ts").write_text("export const SOMETHING = {};\n")
    assert check_flags.problems(root, TODAY) == [
        "could not read a flag registry: no `export const FLAGS = {` found"
    ]
    assert check_flags.stale(root, TODAY) == []
