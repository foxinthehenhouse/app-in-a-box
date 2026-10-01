#!/usr/bin/env python3
"""LIFECYCLE: rank skills and subagents by real use, so "prune the weakest
component" in the harness-optimize skill is a measurement, not a guess.

Model adapted from tigerless-labs/autoharness's lifecycle (MIT):

  - Survival criterion is USE RATE: uses / active days since the component was
    added. Active days = days with a capture log, so a holiday ages nothing.
  - PROBATION: under MATURITY active days old, a component is never a candidate.
    New is not unused.
  - DORMANT: mature, zero uses AND zero views (Reads of its file). A viewed
    component had recall value even without an invocation ("viewed-only").
  - OVER-CAPACITY: when mature, used components exceed the complexity budget
    (`skills` / `agents` in manifest.json), the lowest rates are named.

Report only. It never edits or moves anything: a candidate still goes through
the capability re-test and the manifest's sunset protocol, and protected
components are listed but never candidates.

It refuses (exit 2) on zero capture logs: that means capture is disconnected or
the project is brand new, not that nothing was used.

    python3 .claude/hooks/skill-lifecycle.py               # text report
    python3 .claude/hooks/skill-lifecycle.py --output json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
ROOT = HOOK_DIR.parents[1]
MATURITY = 14  # active days before a component is judged

USE = re.compile(r"^- \d\d:\d\d (?:FAIL )?(?:Skill|Slash) /([A-Za-z0-9_:.-]+)")
AGENT_USE = re.compile(r"^- \d\d:\d\d (?:FAIL )?Agent\[([A-Za-z0-9_:.-]+)\]")
VIEW = re.compile(
    r"^- \d\d:\d\d (?:FAIL )?Read .*?\.(?:agents|claude)/(skills/[^/\s]+/SKILL\.md|agents/[^/\s]+\.md)\s*$"
)


def components(root: Path = ROOT) -> list[dict]:
    out = []
    base = root / ".agents"
    for p in sorted((base / "skills").glob("*/SKILL.md")):
        out.append(
            {"kind": "skills", "name": p.parent.name, "file": p.relative_to(root).as_posix()}
        )
    for p in sorted((base / "agents").glob("*.md")):
        out.append({"kind": "agents", "name": p.stem, "file": p.relative_to(root).as_posix()})
    return out


def added_on(file: str, root: Path = ROOT) -> dt.date | None:
    """First commit that added the file (follows renames). None when git can't say."""
    try:
        r = subprocess.run(
            ["git", "log", "--follow", "--diff-filter=A", "--format=%as", "--", file],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
        )
        dates = r.stdout.split()
        return dt.date.fromisoformat(dates[-1]) if dates else None
    except Exception:
        return None


def read_captures(cap_dir: Path):
    """-> (active days, name -> dates used, component-file -> view count)."""
    days, uses, views = [], {}, {}
    for f in sorted(cap_dir.glob("*-activity.md")):
        try:
            day = dt.date.fromisoformat(f.name[:10])
        except ValueError:
            continue
        days.append(day)
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = USE.match(line) or AGENT_USE.match(line)
            if m:
                uses.setdefault(m.group(1).split(":")[-1], []).append(day)
                continue
            m = VIEW.match(line)
            if m:
                key = ".agents/" + m.group(1)
                views[key] = views.get(key, 0) + 1
    return days, uses, views


def evaluate(comps, days, uses, views, *, protected, capacity, today=None, maturity=MATURITY):
    today = today or dt.date.today()
    rows = []
    for c in comps:
        born = c.get("added") or min(days, default=today)
        active = sum(1 for d in days if d >= born)
        n_use = sum(1 for d in uses.get(c["name"], []) if d >= born)
        row = {
            **c,
            "added": born.isoformat(),
            "active_days": active,
            "uses": n_use,
            "views": views.get(c["file"], 0),
            "rate": round(n_use / active, 3) if active else 0.0,
            "protected": c["file"] in protected,
        }
        if active < maturity:
            row["state"] = "probation"
        elif n_use == 0:
            row["state"] = "dormant" if row["views"] == 0 else "viewed-only"
        else:
            row["state"] = "graduated"
        rows.append(row)
    for kind, cap in capacity.items():
        pool = sorted(
            (r for r in rows if r["kind"] == kind and r["state"] == "graduated"),
            key=lambda r: (r["rate"], r["name"]),
        )
        for r in pool[: max(0, len(pool) - cap)]:
            r["state"] = "over-capacity"
    for r in rows:
        r["candidate"] = r["state"] in ("dormant", "over-capacity") and not r["protected"]
    return rows


def _protected(manifest: dict) -> set[str]:
    out = set()
    for key, items in manifest.items():
        if key.startswith("protected_") and isinstance(items, list):
            out |= {e["file"] for e in items if isinstance(e, dict) and "file" in e}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", choices=["text", "json"], default="text")
    ap.add_argument("--captures", help="override the capture dir (tests)")
    args = ap.parse_args()

    if args.captures:
        cap = Path(args.captures)
    else:
        sys.path.insert(0, str(HOOK_DIR))
        from harness_paths import captures_dir

        cap = Path(captures_dir(str(ROOT)))
    try:
        manifest = json.loads((ROOT / ".claude" / "harness" / "manifest.json").read_text())
    except Exception:
        manifest = {}
    limits = manifest.get("complexity_budget", {}).get("limits", {})
    capacity = {k: limits[k] for k in ("skills", "agents") if k in limits}

    days, uses, views = read_captures(cap) if cap.is_dir() else ([], {}, {})
    if not days:
        print(
            f"REFUSING: no capture logs under {cap}. Zero logs means capture is "
            "disconnected (or the project is brand new), not that nothing was used. "
            "Run the harness-check skill.",
            file=sys.stderr,
        )
        return 2

    comps = components()
    for c in comps:
        c["added"] = added_on(c["file"])
    rows = evaluate(comps, days, uses, views, protected=_protected(manifest), capacity=capacity)

    if args.output == "json":
        print(
            json.dumps(
                {
                    "active_days": len(days),
                    "maturity": MATURITY,
                    "capacity": capacity,
                    "components": rows,
                },
                indent=2,
            )
        )
        return 0

    print(
        f"Skill/agent lifecycle: {len(days)} active days of capture, maturity {MATURITY}d, "
        f"capacity {capacity}"
    )
    order = {"over-capacity": 0, "dormant": 1, "viewed-only": 2, "graduated": 3, "probation": 4}
    for r in sorted(rows, key=lambda r: (order[r["state"]], r["rate"], r["name"])):
        flag = (
            "  <- sunset candidate (capability re-test first)"
            if r["candidate"]
            else (
                "  (protected)"
                if r["protected"] and r["state"] in ("dormant", "over-capacity")
                else ""
            )
        )
        print(
            f"  {r['state']:<13} {r['kind'][:-1]:<6} {r['name']:<28} uses={r['uses']:<3} "
            f"views={r['views']:<3} active_days={r['active_days']:<3} rate={r['rate']:.3f}{flag}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
