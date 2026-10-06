#!/usr/bin/env python3
"""Create an uptime monitor on the deployed API's /health, idempotently, without
printing a token.

    set -a; . ./.env; set +a; python3 uptime_monitor.py --provider betterstack \\
        --api-url "$API_URL" --name "<App name> API"
    set -a; . ./.env; set +a; python3 uptime_monitor.py --provider sentry \\
        --api-url "$API_URL" --name "<App name> API" --org <org slug> --project <slug>-api

Better Stack (free tier) checks `<api>/health?deep=1` every 3 minutes for the keyword
`"status":"ok"`: it alerts when the API is down AND when it's up but degraded (the
database unreachable, a feature's config missing). The deep check pings Postgres, which
also keeps a free Supabase project from pausing.

Sentry Uptime checks `<api>/health` every minute and alerts on a non-2xx answer or a
timeout. /health always answers 200 while the process is up, so Sentry catches "down",
not "degraded". It needs no new account if the app already uses Sentry.

The token comes from the ENVIRONMENT, never an argument: BETTERSTACK_API_TOKEN (Better
Stack → Settings → API tokens, an Uptime token) or SENTRY_AUTH_TOKEN (scope
alerts:write). A monitor already watching the same URL is reused, not duplicated. On
success stdout is one line, `<provider>:<monitor id>`, for appbox.yaml
`resources.uptime`; everything else goes to stderr, with the token scrubbed from any
server reply.

`--dry-run` prints the request it would send, with the token redacted.

Standard library only. Exit 0 ok, 1 request failed, 2 usage or missing env.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

APIS = {"betterstack": "https://uptime.betterstack.com", "sentry": "https://sentry.io"}
TOKEN_ENV = {"betterstack": "BETTERSTACK_API_TOKEN", "sentry": "SENTRY_AUTH_TOKEN"}
KEYWORD = '"status":"ok"'  # the API renders compact JSON; tests/test_health.py pins it
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def scrub(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def health_url(args: argparse.Namespace) -> str:
    base = args.api_url.rstrip("/")
    return (
        f"{base}/health?deep=1" if args.provider == "betterstack" else f"{base}/health"
    )


def plan(args: argparse.Namespace) -> tuple[str, str, dict[str, object]]:
    """(list url, create url, create body) for the provider."""
    url = health_url(args)
    api = args.api.rstrip("/")
    if args.provider == "betterstack":
        listing = f"{api}/api/v2/monitors?" + urllib.parse.urlencode({"url": url})
        body: dict[str, object] = {
            "monitor_type": "keyword",
            "url": url,
            "required_keyword": KEYWORD,
            "pronounceable_name": args.name,
            "check_frequency": 180,  # the free tier's shortest interval
            "request_timeout": 15,
            "confirmation_period": 0,
            "email": True,
        }
        return listing, f"{api}/api/v2/monitors", body
    listing = f"{api}/api/0/organizations/{args.org}/uptime/?" + urllib.parse.urlencode(
        {"query": url}
    )
    body = {
        "name": args.name,
        "url": url,
        "method": "GET",
        "intervalSeconds": 60,
        "timeoutMs": 10000,
        "environment": "production",
    }
    return listing, f"{api}/api/0/projects/{args.org}/{args.project}/uptime/", body


def existing(provider: str, payload: object, url: str) -> str | None:
    """The id of a monitor already watching `url`, from a list response."""
    if provider == "betterstack":
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        for row in rows:
            if (row.get("attributes") or {}).get("url") == url:
                return str(row["id"])
        return None
    for row in payload if isinstance(payload, list) else []:
        if row.get("url") == url:
            return str(row["id"])
    return None


def call(
    method: str, url: str, token: str, body: dict[str, object] | None = None
) -> object:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode() or "null"
    return json.loads(raw)


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create an uptime monitor on /health.")
    p.add_argument("--provider", required=True, choices=sorted(APIS))
    p.add_argument(
        "--api-url", required=True, help="the deployed API's base URL (API_URL)"
    )
    p.add_argument("--name", required=True, help="monitor name, e.g. '<App name> API'")
    p.add_argument("--org", help="Sentry organization slug (sentry only)")
    p.add_argument(
        "--project", help="Sentry project slug, e.g. <slug>-api (sentry only)"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the request, send nothing"
    )
    p.add_argument("--api", help=argparse.SUPPRESS)  # tests point this locally
    args = p.parse_args(argv)
    args.api = args.api or APIS[args.provider]
    if not re.match(r"^https://[^\s/?#]+", args.api_url):
        p.error(f"--api-url {args.api_url!r} must be the deployed https:// URL")
    if args.provider == "sentry":
        for flag in ("org", "project"):
            value = getattr(args, flag)
            if not value or not SLUG.match(value):
                p.error(f"--{flag} is required for sentry and must be a slug")
    return args


def main(argv: list[str]) -> int:
    args = parse(argv)
    env = TOKEN_ENV[args.provider]
    token = os.environ.get(env, "").strip()
    if not token and not args.dry_run:
        print(
            f"uptime_monitor: {env} not set. Add it to .env, then run this as "
            "`set -a; . ./.env; set +a; python3 uptime_monitor.py ...`",
            file=sys.stderr,
        )
        return 2
    listing, create, body = plan(args)
    if args.dry_run:
        print(
            f"GET {listing}\nPOST {create}\nAuthorization: Bearer *** (from {env})",
            file=sys.stderr,
        )
        print(json.dumps(body, indent=2), file=sys.stderr)
        return 0
    url = str(body["url"])
    try:
        found = existing(args.provider, call("GET", listing, token), url)
        if found:
            print(
                f"uptime_monitor: reusing {args.provider} monitor {found} on {url}",
                file=sys.stderr,
            )
        else:
            made = call("POST", create, token, body)
            row = made.get("data", made) if isinstance(made, dict) else {}
            found = str(row["id"])
            print(
                f"uptime_monitor: created {args.provider} monitor {found} on {url}",
                file=sys.stderr,
            )
    except urllib.error.HTTPError as exc:
        detail = scrub(exc.read().decode(errors="replace")[:500], token)
        print(
            f"uptime_monitor: {args.provider} answered {exc.code}: {detail}",
            file=sys.stderr,
        )
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = scrub(str(getattr(exc, "reason", exc)), token)
        print(f"uptime_monitor: couldn't reach {args.api}: {reason}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError) as exc:
        print(
            f"uptime_monitor: unexpected reply from {args.provider} ({exc!r})",
            file=sys.stderr,
        )
        return 1
    print(f"{args.provider}:{found}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
