"""backend/http.py: the one outbound client (timeout, retries, circuit breaker), and the
guard that keeps it the only one.

A bare `httpx.get(...)` / `requests.get(...)` has no retry policy, no breaker, and (with
requests) no timeout at all: one hung upstream holds a worker thread until the platform
kills it. So backend/ may import an HTTP library in exactly one file. Each rule here has
a negative control, and the selftest plants a bare `import httpx` in a router.
"""

from __future__ import annotations

import ast
from pathlib import Path

import httpx
import pytest

from backend import http as outbound

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
THE_CLIENT = "backend/http.py"
BANNED = ("httpx", "requests", "aiohttp", "urllib3", "urllib.request")

# Files that may import an HTTP library anyway, with the reason. Almost nothing belongs
# here: a new upstream (analytics, error tracking, a flags service, a payments API) is a
# `outbound.client("posthog", timeout=...)` call, which gets the timeout, retries and
# breaker for free. List a file only when it can't route through backend/http.py (a
# vendor SDK that owns its transport, say), and say why. Each entry must still exist.
ALLOWED: dict[str, str] = {}


# --- the guard -----------------------------------------------------------------------


def bare_http_imports(source: str) -> list[str]:
    """Imports of an HTTP client library, as `line N: import x`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        else:
            continue
        for name in names:
            if any(name == b or name.startswith(b + ".") for b in BANNED):
                found.append(f"line {node.lineno}: import {name}")
    return found


def test_no_bare_http_client_outside_backend_http() -> None:
    offenders = {
        rel: hits
        for p in sorted(BACKEND.rglob("*.py"))
        if (rel := p.relative_to(ROOT).as_posix()) != THE_CLIENT
        and rel not in ALLOWED
        and (hits := bare_http_imports(p.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        f"bare HTTP client import outside {THE_CLIENT}: {offenders}. Use "
        "`from backend import http as outbound` (mandatory timeout, retries, circuit breaker)."
    )


def test_allowed_entries_are_live_and_justified() -> None:
    for rel, reason in ALLOWED.items():
        assert (ROOT / rel).is_file(), f"{rel}: no such file; drop it from ALLOWED"
        assert len(reason.split()) >= 8, f"{rel}: say why it can't use {THE_CLIENT}"


def test_the_client_itself_is_where_httpx_lives() -> None:
    assert any("import httpx" in h for h in bare_http_imports((ROOT / THE_CLIENT).read_text()))


@pytest.mark.parametrize(
    "src",
    [
        "import httpx\n",
        "import requests as r\n",
        "from httpx import Client\n",
        "from requests.adapters import HTTPAdapter\n",
        "import urllib.request\n",
        "def f():\n    import aiohttp\n",
    ],
)
def test_guard_catches_a_planted_import(src: str) -> None:
    assert bare_http_imports(src)


@pytest.mark.parametrize(
    "src",
    ["from backend import http as outbound\n", "import json\n", "from . import requests_log\n"],
)
def test_guard_ignores_the_sanctioned_and_unrelated(src: str) -> None:
    assert bare_http_imports(src) == []


# --- the client ----------------------------------------------------------------------


class Upstream:
    """A scripted MockTransport: each item is a status code or an exception to raise."""

    def __init__(self, *script: int | Exception) -> None:
        self.script: list[int | Exception] = list(script)
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        step = self.script.pop(0) if self.script else 200
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step, json={"ok": step < 400})


def _client(up: Upstream, **kw: object) -> outbound.Client:
    sleeps: list[float] = []
    c = outbound.client(
        "test-upstream",
        timeout=5,
        transport=httpx.MockTransport(up),
        base_url="https://up.example",
        sleep=sleeps.append,
        **kw,  # type: ignore[arg-type]
    )
    c.sleeps = sleeps  # type: ignore[attr-defined]
    return c


@pytest.mark.parametrize("timeout", [0, -1, None])
def test_a_timeout_is_mandatory(timeout: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        outbound.client("x", timeout=timeout)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        outbound.client("x")  # type: ignore[call-arg]


def test_connect_errors_are_retried_for_any_method() -> None:
    up = Upstream(httpx.ConnectError("refused"), httpx.ConnectTimeout("slow"), 201)
    c = _client(up)
    assert c.post("/things", json={}).status_code == 201
    assert len(up.calls) == 3
    assert len(c.sleeps) == 2  # type: ignore[attr-defined]


def test_connect_errors_past_the_last_attempt_raise() -> None:
    up = Upstream(*[httpx.ConnectError("refused")] * 3)
    with pytest.raises(httpx.ConnectError):
        _client(up).get("/x")
    assert len(up.calls) == 3


def test_5xx_is_retried_for_an_idempotent_method() -> None:
    up = Upstream(503, 502, 200)
    assert _client(up).get("/x").status_code == 200
    assert len(up.calls) == 3


def test_5xx_on_a_plain_post_is_not_repeated() -> None:
    # The POST may have run before the 5xx: sending it again could charge twice.
    up = Upstream(503, 200)
    assert _client(up).post("/charge", json={}).status_code == 503
    assert len(up.calls) == 1


def test_5xx_on_a_post_with_an_idempotency_key_or_flag_is_retried() -> None:
    up = Upstream(500, 200)
    resp = _client(up).post("/charge", json={}, headers={"Idempotency-Key": "k-12345678"})
    assert resp.status_code == 200 and len(up.calls) == 2
    up = Upstream(500, 200)
    assert _client(up).post("/receipts", json={}, idempotent=True).status_code == 200


def test_read_timeouts_are_not_repeated() -> None:
    up = Upstream(httpx.ReadTimeout("stalled"), 200)
    with pytest.raises(httpx.ReadTimeout):
        _client(up).get("/x")
    assert len(up.calls) == 1


def test_4xx_is_returned_at_once() -> None:
    up = Upstream(404)
    assert _client(up).get("/x").status_code == 404
    assert len(up.calls) == 1


def test_backoff_is_jittered_and_capped() -> None:
    assert outbound.backoff(0, 0.2, 2.0, rand=lambda: 1.0) == pytest.approx(0.2)
    assert outbound.backoff(3, 0.2, 2.0, rand=lambda: 1.0) == pytest.approx(1.6)
    assert outbound.backoff(10, 0.2, 2.0, rand=lambda: 1.0) == 2.0
    assert outbound.backoff(3, 0.2, 2.0, rand=lambda: 0.0) == 0.0


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_breaker_opens_fails_fast_then_trials_one_call() -> None:
    clock = Clock()
    breaker = outbound.CircuitBreaker(threshold=2, reset_after=30, clock=clock)
    up = Upstream(*[httpx.ConnectError("down")] * 6)
    c = _client(up, attempts=1, breaker=breaker)
    for _ in range(2):
        with pytest.raises(httpx.ConnectError):
            c.get("/x")
    assert breaker.is_open
    with pytest.raises(outbound.CircuitOpen):
        c.get("/x")
    assert len(up.calls) == 2  # refused without sending
    clock.now += 31
    assert breaker.allow() and not breaker.allow()  # half-open: one trial at a time
    breaker.record(False)  # the trial failed: open again, for another reset_after
    with pytest.raises(outbound.CircuitOpen):
        c.get("/x")
    clock.now += 31
    up.script = [200]
    assert c.get("/x").status_code == 200
    assert not breaker.is_open


def test_circuit_open_is_handled_as_unreachable() -> None:
    # Callers already catch HTTPError for "upstream unreachable"; an open circuit is that.
    assert issubclass(outbound.CircuitOpen, outbound.HTTPError)


def test_a_5xx_after_retries_counts_against_the_breaker_and_a_2xx_resets_it() -> None:
    breaker = outbound.CircuitBreaker(threshold=2, clock=Clock())
    c = _client(Upstream(500, 500, 500, 200), attempts=1, breaker=breaker)
    c.get("/x")
    c.get("/x")
    assert breaker.is_open
    breaker2 = outbound.CircuitBreaker(threshold=2, clock=Clock())
    c2 = _client(Upstream(500, 200, 500), attempts=1, breaker=breaker2)
    for _ in range(3):
        c2.get("/x")
    assert not breaker2.is_open  # failures must be consecutive


def test_our_own_bug_leaves_no_verdict_on_the_upstream() -> None:
    breaker = outbound.CircuitBreaker(threshold=1, reset_after=1, clock=(clock := Clock()))
    breaker.record(False)
    clock.now += 2

    def broken(_r: httpx.Request) -> httpx.Response:
        raise ValueError("bad request object")

    c = outbound.client("t", timeout=5, transport=httpx.MockTransport(broken), breaker=breaker)
    with pytest.raises(ValueError):
        c.get("https://up.example/x")
    assert breaker.allow()  # the trial slot was freed, not stuck taken


def test_breakers_are_per_upstream_name_and_resettable() -> None:
    a = outbound.client("svc-a", timeout=1).breaker
    assert outbound.client("svc-a", timeout=1).breaker is a
    assert outbound.client("svc-b", timeout=1).breaker is not a
    outbound.reset_breakers()
    assert outbound.client("svc-a", timeout=1).breaker is not a


def test_breaker_rejects_nonsense_settings() -> None:
    with pytest.raises(ValueError):
        outbound.CircuitBreaker(threshold=0)
    with pytest.raises(ValueError):
        outbound.client("x", timeout=1, attempts=0)


def test_module_get_uses_the_same_policy() -> None:
    up = Upstream(503, 200)
    resp = outbound.get("one-shot", "https://up.example/x", timeout=1, transport=httpx.MockTransport(up))
    assert resp.status_code == 200 and len(up.calls) == 2
