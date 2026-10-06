"""Feature flags and kill switches for the API: `flag("kill-push", user_id)`.

The same PostHog flags the app reads (mobile/lib/flags.ts), evaluated server side, so
one switch in PostHog turns a feature off on both ends.

Every flag is registered in FLAGS with a safe default, an owner and an expiry date.
`scripts/check_flags.py` (CI) fails on a flag without them, and the `next` skill
surfaces flags past their expiry, so a flag gets removed instead of living forever.

Resolution, first answer wins:
1. `FLAG_<NAME>` env var (`FLAG_KILL_PUSH=1`): the emergency lever when PostHog itself
   is the problem. A Railway variable change redeploys in a minute or two.
2. PostHog, when POSTHOG_API_KEY is set and the call names a user. One HTTP call per
   `flag()` (no cache: the API runs several workers, and a per-process cache would
   disagree with itself) through backend/http.py with a 1s timeout and no retry, so a
   dead PostHog costs a request at most about a second; after a few failures the
   circuit opens and lookups skip PostHog entirely. Call it once per request, not in a
   loop.
3. The registered default. Without a key (dev, demo, an app without analytics) every
   flag is its default, so nothing depends on PostHog being reachable.

Kill switches are named `kill-<feature>` and default to False: turning the PostHog
flag ON turns the feature OFF, and a flag that is missing, deleted or unreachable
leaves the feature running.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from backend import http as outbound
from backend.config import env, feature_missing

logger = logging.getLogger(__name__)

FEATURE: Final = "feature flags (PostHog)"
TIMEOUT_SECONDS: Final = 1.0
UPSTREAM: Final = "posthog-flags"  # the circuit breaker's name in backend/http.py

# Tests set this to an httpx.MockTransport; None sends for real.
_transport: outbound.Transport | None = None


@dataclass(frozen=True)
class Flag:
    default: bool | str
    owner: str  # who decides when it goes: "@handle"
    expires: str  # YYYY-MM-DD: remove the flag (or extend it, at most a year) by then
    description: str
    kill_switch: bool = False


# Keep in step with FLAGS in mobile/lib/flags.ts for flags both sides read.
FLAGS: Final[dict[str, Flag]] = {
    "kill-push": Flag(
        default=False,
        owner="@__OWNER__",
        expires="2027-09-30",
        description="Stops every push send (a bad cron, a spam loop). The app pauses its toggle.",
        kill_switch=True,
    ),
}


def _env_name(name: str) -> str:
    return "FLAG_" + name.upper().replace("-", "_")


def _coerce(spec: Flag, value: object) -> bool | str | None:
    """A raw value in the flag's own type, or None when it doesn't fit."""
    if isinstance(spec.default, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in {"1", "true", "on", "yes"}:
                return True
            if low in {"0", "false", "off", "no"}:
                return False
            return True if low else None  # a multivariate variant counts as on
        return None
    return value if isinstance(value, str) and value else None


def _from_posthog(name: str, distinct_id: str) -> object:
    host = (env("POSTHOG_HOST") or "https://us.i.posthog.com").rstrip("/")
    try:
        resp = outbound.post(
            UPSTREAM,
            f"{host}/flags/?v=2",
            json={"api_key": env("POSTHOG_API_KEY"), "distinct_id": distinct_id},
            timeout=TIMEOUT_SECONDS,
            attempts=1,  # a flag is never worth a retry: the default is a fine answer
            transport=_transport,
        )
        resp.raise_for_status()
        detail = (resp.json().get("flags") or {}).get(name)
    except Exception as exc:  # PostHog down (or its circuit open) must never take the API down
        logger.warning(
            "flag %s: PostHog unavailable (%s); using the default", name, type(exc).__name__
        )
        return None
    if not isinstance(detail, dict):
        return None  # not defined in PostHog: the default stands
    if not detail.get("enabled"):
        return False
    return detail.get("variant") or True


def flag(name: str, distinct_id: str | None = None) -> bool | str:
    """The flag's value for this user (the user id the app identifies with)."""
    spec = FLAGS[name]  # KeyError: register the flag first
    override = env(_env_name(name))
    if override:
        value = _coerce(spec, override)
        if value is not None:
            return value
        logger.warning("%s=%r doesn't fit flag %s; ignoring it", _env_name(name), override, name)
    if distinct_id and not feature_missing(FEATURE):
        value = _coerce(spec, _from_posthog(name, distinct_id))
        if value is not None:
            return value
    return spec.default


def enabled(name: str, distinct_id: str | None = None) -> bool:
    """`flag()` for a boolean flag. True means the flag is on (for a kill switch: killed)."""
    return flag(name, distinct_id) is True
