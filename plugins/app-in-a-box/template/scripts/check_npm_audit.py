#!/usr/bin/env python3
"""Fail on high or critical npm advisories in the mobile app, unless triaged.

Runs `npm audit --omit=dev --json` in mobile/ (or reads a saved report) and fails on
every high/critical advisory that mobile/npm-audit-allowlist.json does not list.
Dev-only packages (jest, eslint) never reach a phone, so they are left out.

Why an allowlist and not a bare `npm audit --audit-level=high`: a freshly scaffolded
Expo app already reports dozens of high advisories in the SDK's own build tooling
(@expo/cli, code signing), and `npm audit fix` "fixes" them by downgrading Expo by
ten majors. A gate that is red from day one gets ignored. So each advisory is looked
at once, by a person, and either fixed or written down:

    {
      "GHSA-xxxx-xxxx-xxxx": {
        "package": "braces",
        "reason": "Pulled in by the Expo build tooling; not in the app bundle. No SDK release fixes it yet.",
        "until": "2026-12-01"
      }
    }

`until` is at most 90 days out: past it the entry fails again and gets re-triaged
(the weekly dependency-triage routine sees it first). An entry whose advisory is no
longer reported is printed so you can delete it.

Usage:
    python3 scripts/check_npm_audit.py                 # run npm audit in mobile/
    python3 scripts/check_npm_audit.py report.json     # check a saved `npm audit --json`
Run by .github/workflows/security.yml. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = "mobile/npm-audit-allowlist.json"
BLOCKING = {"high", "critical"}
MAX_DAYS = 90


def advisories(report: dict[str, Any]) -> dict[str, dict[str, str]]:
    """{advisory id: {package, severity, title, url}} for every high/critical advisory."""
    if "error" in report or "vulnerabilities" not in report:
        raise ValueError(f"not an npm audit report: {json.dumps(report)[:300]}")
    found: dict[str, dict[str, str]] = {}
    for vuln in report["vulnerabilities"].values():
        for via in vuln.get("via", []):
            # A string `via` is "vulnerable because of that package": the advisory
            # itself is reported on that package's own entry.
            if not isinstance(via, dict) or via.get("severity") not in BLOCKING:
                continue
            url = str(via.get("url", ""))
            key = url.rsplit("/", 1)[-1] if "/advisories/" in url else str(via.get("source"))
            found[key] = {
                "package": str(via.get("name", vuln.get("name", "?"))),
                "severity": str(via["severity"]),
                "title": str(via.get("title", "")),
                "url": url,
            }
    return found


def check(
    found: dict[str, dict[str, str]], allow: dict[str, Any], today: dt.date
) -> tuple[list[str], list[str]]:
    """(problems, notes). Problems fail the build; notes are housekeeping."""
    problems: list[str] = []
    notes: list[str] = []
    for key, entry in sorted(allow.items()):
        if not isinstance(entry, dict):
            problems.append(f"{ALLOWLIST}: {key} must be an object with package, reason, until")
            continue
        reason = str(entry.get("reason", "")).strip()
        if len(reason) < 20:
            problems.append(f"{ALLOWLIST}: {key} needs a reason (why it is safe to ship for now)")
        try:
            until = dt.date.fromisoformat(str(entry.get("until")))
        except ValueError:
            problems.append(f"{ALLOWLIST}: {key} needs `until` as YYYY-MM-DD")
            continue
        if until < today:
            problems.append(
                f"{ALLOWLIST}: {key} expired on {until}; re-triage it (fix, or a new date)"
            )
        elif (until - today).days > MAX_DAYS:
            problems.append(f"{ALLOWLIST}: {key} `until` {until} is more than {MAX_DAYS} days out")
        if key not in found:
            notes.append(f"{key} is no longer reported; delete it from {ALLOWLIST}")
    for key, adv in sorted(found.items()):
        if key not in allow:
            problems.append(
                f"{adv['severity']} {key} in {adv['package']}: {adv['title']} ({adv['url']}). "
                f"Upgrade the package that pulls it in, or triage it in {ALLOWLIST}"
            )
    return problems, notes


def run_audit(root: Path) -> dict[str, Any]:
    # npm audit exits 1 when it finds anything; the JSON on stdout is the result.
    out = subprocess.run(
        ["npm", "audit", "--omit=dev", "--json"],
        cwd=root / "mobile",
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"npm audit printed no JSON (exit {out.returncode}): {out.stderr[-500:]}"
        ) from e


def main(argv: list[str]) -> int:
    try:
        report = json.loads(Path(argv[0]).read_text()) if argv else run_audit(ROOT)
        found = advisories(report)
    except (OSError, ValueError) as e:
        # A scanner that could not run is a failure, never a pass.
        print(f"check_npm_audit: {e}")
        return 1
    path = ROOT / ALLOWLIST
    allow = json.loads(path.read_text()) if path.exists() else {}
    problems, notes = check(found, allow, dt.date.today())
    for n in notes:
        print(f"check_npm_audit: note: {n}")
    for p in problems:
        print(f"check_npm_audit: {p}")
    if not problems:
        print(f"check_npm_audit: no untriaged high/critical advisories ({len(found)} triaged)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
