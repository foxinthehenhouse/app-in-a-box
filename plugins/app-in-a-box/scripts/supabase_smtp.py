#!/usr/bin/env python3
"""Point a hosted Supabase project's auth email at custom SMTP, without printing a secret.

    set -a; . ./.env; set +a; python3 supabase_smtp.py --ref <ref> --resend \\
        --sender-email no-reply@<your domain> --sender-name "<App name>" \\
        | python3 env_set.py .env

Supabase sends the sign-in (OTP) email, not the app's API. Its built-in mailer allows
only a couple of emails an hour and new projects can't edit their email templates
without custom SMTP, so real users can't sign in until this has run. Resend's free tier
(100 emails/day) works as Supabase custom SMTP: host smtp.resend.com, port 465, user
"resend", password = a Resend API key.

Both secrets come from the ENVIRONMENT, never from arguments (argv shows up in `ps` and
in the transcript): SUPABASE_ACCESS_TOKEN (a personal access token, for the Management
API) and SMTP_PASS (for Resend, the API key). The request body is built here and sent
with urllib, so neither ever lands on a command line. On success stdout is one line,
`AUTH_SMTP_HOST=<host>`: not a secret, it's the marker the API's /health reads, ready to
pipe into env_set.py. Everything else goes to stderr, and any server reply is scrubbed of
both secrets before it's shown.

`--dry-run` prints the request it would send, with the password and token redacted.

Standard library only. Exit 0 ok, 1 request failed, 2 usage or missing env.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.supabase.com"
RESEND = {"host": "smtp.resend.com", "port": "465", "user": "resend"}
REF = re.compile(r"^[a-z0-9]{8,40}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
SECRET_ENV = ("SMTP_PASS", "SUPABASE_ACCESS_TOKEN")


def scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def payload(args: argparse.Namespace, password: str) -> dict[str, object]:
    """The PATCH /v1/projects/{ref}/config/auth body. Field names and types follow the
    Management API's UpdateAuthConfigBody (smtp_port is a string there)."""
    body: dict[str, object] = {
        "external_email_enabled": True,
        "smtp_host": args.host,
        "smtp_port": str(args.port),
        "smtp_user": args.user,
        "smtp_pass": password,
        "smtp_admin_email": args.sender_email,
        "smtp_sender_name": args.sender_name,
    }
    if args.rate_limit:
        body["rate_limit_email_sent"] = args.rate_limit
    return body


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Configure Supabase Auth custom SMTP.")
    p.add_argument("--ref", required=True, help="Supabase project ref")
    p.add_argument("--resend", action="store_true", help="use Resend's SMTP settings")
    p.add_argument("--host", help="SMTP host (any provider)")
    p.add_argument("--port", help="SMTP port, e.g. 465 or 587")
    p.add_argument("--user", help="SMTP username")
    p.add_argument(
        "--sender-email", required=True, help="From address on a verified domain"
    )
    p.add_argument(
        "--sender-name", required=True, help="From name, usually the app's name"
    )
    p.add_argument(
        "--rate-limit", type=int, help="auth emails per hour (Supabase default 30)"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="print the request, send nothing"
    )
    p.add_argument(
        "--api", default=API, help=argparse.SUPPRESS
    )  # tests point this locally
    args = p.parse_args(argv)
    if args.resend:
        for k, v in RESEND.items():
            setattr(args, k, getattr(args, k) or v)
    missing = [f"--{k}" for k in ("host", "port", "user") if not getattr(args, k)]
    if missing:
        p.error(f"{', '.join(missing)} required (or --resend)")
    if not REF.match(args.ref):
        p.error(f"--ref {args.ref!r} doesn't look like a project ref")
    if not EMAIL.match(args.sender_email):
        p.error(f"--sender-email {args.sender_email!r} isn't an email address")
    if not str(args.port).isdigit():
        p.error(f"--port {args.port!r} isn't a number")
    return args


def main(argv: list[str]) -> int:
    args = parse(argv)
    secrets = {name: os.environ.get(name, "").strip() for name in SECRET_ENV}
    unset = [name for name in SECRET_ENV if not secrets[name]]
    if unset and not args.dry_run:
        print(
            f"supabase_smtp: {' and '.join(unset)} not set. Add to .env, then run this as "
            "`set -a; . ./.env; set +a; python3 supabase_smtp.py ...`",
            file=sys.stderr,
        )
        return 2
    if not secrets["SMTP_PASS"] and args.dry_run:
        print("supabase_smtp: SMTP_PASS not set (dry run continues)", file=sys.stderr)
    body = payload(args, secrets["SMTP_PASS"])
    url = f"{args.api.rstrip('/')}/v1/projects/{args.ref}/config/auth"
    if args.dry_run:
        shown = {**body, "smtp_pass": "*** (from SMTP_PASS)"}
        print(
            f"PATCH {url}\nAuthorization: Bearer *** (from SUPABASE_ACCESS_TOKEN)",
            file=sys.stderr,
        )
        print(json.dumps(shown, indent=2), file=sys.stderr)
        return 0
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="PATCH",
        headers={
            "Authorization": f"Bearer {secrets['SUPABASE_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        detail = scrub(
            exc.read().decode(errors="replace")[:500], list(secrets.values())
        )
        print(f"supabase_smtp: Supabase answered {exc.code}: {detail}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = scrub(str(getattr(exc, "reason", exc)), list(secrets.values()))
        print(f"supabase_smtp: couldn't reach {args.api}: {reason}", file=sys.stderr)
        return 1
    print(
        f"supabase_smtp: project {args.ref} now sends auth email through "
        f"{args.host}:{args.port} as {args.user!r} from {args.sender_email} "
        "(password from SMTP_PASS, not shown)",
        file=sys.stderr,
    )
    print(f"AUTH_SMTP_HOST={args.host}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
