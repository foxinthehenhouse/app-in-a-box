#!/usr/bin/env python3
"""Check the intake's two contracts: the brief's decision ledger, and DEFAULTS.md.

    check_intake.py brief design/brief.json
    check_intake.py defaults docs/DEFAULTS.md --root <app or template dir>

`brief`: design/brief.json carries the decision ledger and the day-0 sections every
later phase reads (schema in docs/COST.md -> "The brief"). A brief without them reads
as "nothing was decided", and the phases that should ask a deferred decision never
see it. It also caps the questions shape actually asked at 7: the rest are stated
defaults or deferred to the phase where they matter.

`defaults`: every row of docs/DEFAULTS.md names where the default lives (backticked
paths, relative to the app root) or says it is "on the roadmap". A path that doesn't
exist is a claim the template can't back, so it fails.

Prints one line per problem and exits 1, or exits 0 silently. Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STATUSES = ("asked", "default", "deferred")
PHASES = (
    "shape",
    "prototype",
    "scaffold",
    "first-feature",
    "pre-launch",
    "post-launch",
)
SOCIAL = ("solo", "shared", "community", "two_sided")
MONEY = ("free", "subscription", "one_off", "ads", "b2b")
DAY0_SECTIONS = ("context", "payoff", "social", "distribution", "money")
DECISION_KEYS = ("id", "question", "answer", "status", "ask_at", "why")
MAX_ASKED_AT_SHAPE = 7
ROADMAP = "on the roadmap"


def check_brief(brief: object) -> list[str]:
    if not isinstance(brief, dict):
        return ["brief: not a JSON object"]
    out: list[str] = []
    for key in DAY0_SECTIONS:
        if key not in brief:
            out.append(
                f"brief: no `{key}` section (a day-0 question: ask it, assume it, or say why not)"
            )
    social = brief.get("social")
    if isinstance(social, dict) and social.get("shape") not in (None, *SOCIAL):
        out.append(
            f"brief: social.shape {social.get('shape')!r} is not one of {', '.join(SOCIAL)}"
        )
    money = brief.get("money")
    if isinstance(money, dict) and money.get("model") not in (None, *MONEY):
        out.append(
            f"brief: money.model {money.get('model')!r} is not one of {', '.join(MONEY)}"
        )
    decisions = brief.get("decisions")
    if not isinstance(decisions, list):
        return [
            *out,
            "brief: no `decisions` ledger (a list; see docs/COST.md -> The brief)",
        ]
    seen: set[str] = set()
    asked_at_shape = 0
    for i, d in enumerate(decisions):
        if not isinstance(d, dict):
            out.append(f"decisions[{i}]: not an object")
            continue
        name = d.get("id") or f"decisions[{i}]"
        missing = [k for k in DECISION_KEYS if k not in d]
        if missing:
            out.append(f"{name}: missing {', '.join(missing)}")
        if d.get("id") in seen:
            out.append(f"{name}: duplicate id")
        seen.add(str(d.get("id")))
        status, ask_at = d.get("status"), d.get("ask_at")
        if status not in STATUSES:
            out.append(f"{name}: status {status!r} is not one of {', '.join(STATUSES)}")
        if ask_at not in PHASES:
            out.append(f"{name}: ask_at {ask_at!r} is not one of {', '.join(PHASES)}")
        if status in ("asked", "default") and not d.get("answer"):
            out.append(f"{name}: status {status} needs an answer")
        if status == "deferred" and ask_at == "shape":
            out.append(
                f"{name}: deferred to shape, which is now: ask it, assume it, or defer it to a later phase"
            )
        if not d.get("why"):
            out.append(f"{name}: no `why` (what the answer changes)")
        if status == "asked" and ask_at == "shape":
            asked_at_shape += 1
    if asked_at_shape > MAX_ASKED_AT_SHAPE:
        out.append(
            f"decisions: {asked_at_shape} asked at shape, the cap is {MAX_ASKED_AT_SHAPE}: "
            "state the rest as defaults or defer them to the phase where they matter"
        )
    return out


def check_defaults(text: str, root: Path) -> list[str]:
    out: list[str] = []
    rows = [
        ln
        for ln in text.splitlines()
        if ln.startswith("|") and not re.match(r"^\|[\s|:-]+\|$", ln)
    ]
    if len(rows) < 2:
        return ["DEFAULTS.md: no table of defaults"]
    for row in rows[1:]:  # rows[0] is the header
        name = row.strip("|").split("|")[0].strip() or row
        paths = [
            p
            for p in re.findall(r"`([^`\s]+)`", row)
            if "/" in p or re.search(r"\.\w+$", p)
        ]
        if not paths and ROADMAP not in row.lower():
            out.append(f"{name}: names no file and doesn't say it's {ROADMAP}")
        for p in paths:
            if not (root / p.split("#")[0].rstrip("/")).exists():
                out.append(f"{name}: `{p}` doesn't exist under {root}")
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "brief":
        try:
            brief = json.loads(Path(argv[1]).read_text())
        except (OSError, ValueError) as e:
            print(f"brief: can't read {argv[1]}: {e}")
            return 1
        problems = check_brief(brief)
    elif len(argv) >= 2 and argv[0] == "defaults":
        root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path(".")
        problems = check_defaults(Path(argv[1]).read_text(), root)
    else:
        print("\n".join(__doc__.strip().splitlines()[2:4]))
        return 2
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
