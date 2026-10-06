"""The one outbound HTTP client. Every call this API makes to another service goes here.

    from backend import http as outbound

    with outbound.client("expo-push", base_url=EXPO_BASE, timeout=15) as c:
        resp = c.post("/send", json=messages)

Three things a bare `httpx.get(...)` gets wrong, done once:

- **A timeout, always.** `timeout` is a required keyword with no default. httpx's own
  default is 5s, but `requests` has none at all, and one hung upstream holds a worker
  thread until the platform kills it. A guard (tests/test_outbound_http.py) fails on
  `import httpx` / `import requests` anywhere in backend/ except this file.
- **Retries that can't double-send.** A connect error means the request never left, so
  it is retried for any method. A 5xx is retried only when repeating the request is
  safe: an idempotent method (GET, HEAD, OPTIONS, PUT, DELETE), a request carrying an
  `Idempotency-Key`, or `idempotent=True` from a caller that knows (a read sent as POST).
  Backoff is exponential with full jitter, so a fleet of workers doesn't retry in step.
- **A circuit breaker per upstream.** After `failure_threshold` consecutive failures (a
  connect error or a 5xx, after retries) the breaker opens and calls fail fast with
  `CircuitOpen` for `reset_after` seconds, instead of every request waiting out the
  timeout on a service that is down. Then one trial call goes through: success closes
  it, failure opens it again.

`CircuitOpen` is an `httpx.TransportError`, so a caller that already handles "the
upstream is unreachable" (`except outbound.HTTPError`) handles an open circuit too.

⚖️ The breaker is per worker process (one per upstream name, `_breaker()`), the one
deliberate exception to "no in-process state": it holds this process's recent failures
for a host, nothing about any user. Workers disagreeing costs at most `failure_threshold`
slow calls each. A shared breaker would need a Postgres round trip on every call.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Re-exported so callers never import httpx themselves (the guard bans it).
HTTPError = httpx.HTTPError
Response = httpx.Response
Transport = httpx.BaseTransport

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
DEFAULT_ATTEMPTS = 3  # the first try plus two retries
DEFAULT_BASE_DELAY = 0.2  # seconds; attempt n waits up to base * 2**n
DEFAULT_MAX_DELAY = 2.0
FAILURE_THRESHOLD = 5
RESET_AFTER = 30.0  # seconds an open circuit fails fast before one trial call


class CircuitOpen(httpx.TransportError):
    """The upstream failed repeatedly; this call was refused without being sent."""


def backoff(
    attempt: int, base: float, cap: float, rand: Callable[[], float] = random.random
) -> float:
    """Full-jitter delay before retry number `attempt` (0-based): uniform in [0, min(cap, base*2^n)]."""
    return rand() * min(cap, base * (2**attempt))


class CircuitBreaker:
    """Closed -> open after `threshold` consecutive failures -> one trial after `reset_after`."""

    def __init__(
        self,
        threshold: int = FAILURE_THRESHOLD,
        reset_after: float = RESET_AFTER,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if threshold < 1 or reset_after <= 0:
            raise ValueError("threshold must be >= 1 and reset_after > 0")
        self.threshold = threshold
        self.reset_after = reset_after
        self._clock = clock
        self._lock = threading.Lock()  # the threadpool runs handlers concurrently
        self._failures = 0
        self._opened_at: float | None = None
        self._trial = False

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None

    def retry_in(self) -> float:
        """Seconds until an open circuit lets a trial call through (0 when closed)."""
        if self._opened_at is None:
            return 0.0
        return max(0.0, self.reset_after - (self._clock() - self._opened_at))

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if self._trial or self._clock() - self._opened_at < self.reset_after:
                return False
            self._trial = True  # half-open: exactly one call finds out
            return True

    def abandon(self) -> None:
        """A call ended without telling us anything about the upstream: free the trial slot."""
        with self._lock:
            self._trial = False

    def record(self, ok: bool) -> None:
        with self._lock:
            self._trial = False
            if ok:
                self._failures, self._opened_at = 0, None
                return
            self._failures += 1
            if self._opened_at is not None or self._failures >= self.threshold:
                self._opened_at = self._clock()


@lru_cache(maxsize=64)
def _breaker(name: str) -> CircuitBreaker:
    return CircuitBreaker()


def reset_breakers() -> None:
    """Close every circuit (tests, or after fixing an upstream by hand)."""
    _breaker.cache_clear()


class Client:
    """An httpx.Client with retries and a breaker. Build it with `client(...)`."""

    def __init__(
        self,
        name: str,
        *,
        timeout: float,
        base_url: str = "",
        headers: Mapping[str, str] | None = None,
        transport: Transport | None = None,
        attempts: int = DEFAULT_ATTEMPTS,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        breaker: CircuitBreaker | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(timeout, int | float) or timeout <= 0:
            raise ValueError("an outbound call needs a positive timeout, in seconds")
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        self.name = name
        self.attempts = attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.breaker = breaker or _breaker(name)
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=base_url, headers=dict(headers or {}), timeout=timeout, transport=transport
        )

    def request(
        self, method: str, url: str, *, idempotent: bool | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send with retries. Returns the final response (a 5xx included, for the caller to
        judge); raises the last transport error, or CircuitOpen without sending."""
        method = method.upper()
        if not self.breaker.allow():
            raise CircuitOpen(f"{self.name}: circuit open, retry in {self.breaker.retry_in():.0f}s")
        if idempotent is None:
            headers = {k.lower() for k in (kwargs.get("headers") or {})}
            idempotent = method in IDEMPOTENT_METHODS or "idempotency-key" in headers
        for attempt in range(self.attempts):
            last = attempt == self.attempts - 1
            try:
                resp = self._http.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Never reached the server: safe to repeat whatever the method.
                if last:
                    self.breaker.record(False)
                    raise
                logger.info("%s: %s, retrying", self.name, type(exc).__name__)
            except httpx.TransportError:
                self.breaker.record(False)  # read timeout etc.: it may have run; don't repeat
                raise
            except Exception:
                self.breaker.abandon()  # our bug (a bad URL), not the upstream's: no verdict
                raise
            else:
                if resp.status_code < 500:
                    self.breaker.record(True)
                    return resp
                if last or not idempotent:
                    self.breaker.record(False)
                    return resp
                resp.close()
                logger.info("%s: HTTP %d, retrying", self.name, resp.status_code)
            self._sleep(backoff(attempt, self.base_delay, self.max_delay))
        raise AssertionError("unreachable")  # pragma: no cover

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def client(name: str, *, timeout: float, **kwargs: Any) -> Client:
    """A client for one upstream. `name` keys its circuit breaker ("expo-push", "stripe")."""
    return Client(name, timeout=timeout, **kwargs)


def request(
    name: str,
    method: str,
    url: str,
    *,
    timeout: float,
    transport: Transport | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    **kwargs: Any,
) -> httpx.Response:
    """One call through a short-lived client (same retries and breaker as `client`).
    `attempts=1` for a fire-and-forget call that must not outlast its timeout."""
    with client(name, timeout=timeout, transport=transport, attempts=attempts) as c:
        return c.request(method, url, **kwargs)


def get(name: str, url: str, *, timeout: float, **kwargs: Any) -> httpx.Response:
    return request(name, "GET", url, timeout=timeout, **kwargs)


def post(name: str, url: str, *, timeout: float, **kwargs: Any) -> httpx.Response:
    return request(name, "POST", url, timeout=timeout, **kwargs)
