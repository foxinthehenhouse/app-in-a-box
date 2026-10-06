#!/usr/bin/env python3
"""Gather the signals the `next` skill ranks. Standard library only; fails open.

    python3 .agents/skills/next/signals.py            # JSON, local signals only (fast)
    python3 .agents/skills/next/signals.py --remote   # + open PRs, failing CI, issues (gh)
    python3 .agents/skills/next/signals.py --line     # one line for the SessionStart hook

Local signals never touch the network, so the SessionStart line stays instant.
PostHog and Linear are read by the agent through MCP; this script only reports
whether they're configured.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[3])
SETUP = [  # must match the kit's progress.py PHASES keys (selftest-checked)
    "preflight", "interview", "validate", "design", "accounts", "scaffold",
    "provision", "harness", "verify", "first_feature",
]  # fmt: skip
DONE = {"done", "true", "yes", "skipped"}
# The brief's decision ledger (design/brief.json -> decisions, schema in the kit's
# docs/COST.md): a `deferred` decision is due once its `ask_at` phase has arrived.
DECISION_PHASES = ["shape", "prototype", "scaffold", "first-feature", "pre-launch", "post-launch"]
RITUALS = [  # (ritual, manifest cadence key, default days)
    ("reflect", "reflect_days", 10),
    ("harness-optimize", "optimize_days", 7),
    ("north-star-report", "north_star_days", 7),
    ("market-watch", "market_watch_days", 30),  # only once the owner sets the cadence
]


def sh(*cmd: str, timeout: float = 4.0) -> str | None:
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def appbox() -> dict:
    """Flat read of appbox.yaml: progress + stack.tracker/analytics."""
    out: dict = {"progress": {}, "stack": {}}
    try:
        text = (ROOT / "appbox.yaml").read_text()
    except OSError:
        return out
    section = None
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        if indent == 0:
            section = key
        elif indent == 2 and section in out:
            out[section][key] = value.strip().strip("\"'").lower()
    return out


def rituals() -> list[dict]:
    try:
        sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
        import harness_paths as hp  # type: ignore

        state = hp.load_state(str(ROOT))
        manifest = json.loads((ROOT / ".claude" / "harness" / "manifest.json").read_text())
    except Exception:
        return []
    import datetime

    cadence = manifest.get("cadence", {})
    last = state.get("last_run", {})
    anchor = state.get("installed")
    out = []
    scheduled = set(cadence.get("scheduled", []))  # a Routine/cron runs these
    for name, key, default in RITUALS:
        if name in scheduled or (
            key not in cadence and name not in ("reflect", "harness-optimize")
        ):
            continue
        limit = cadence.get(key, default)
        ts = last.get(name) or anchor
        try:
            age = (datetime.datetime.now() - datetime.datetime.fromisoformat(ts)).days
        except Exception:
            age = None
        if age is not None and age >= limit:
            out.append({"ritual": name, "days_since": age, "cadence_days": limit,
                        "never_run": name not in last})  # fmt: skip
    return out


def decisions_due(prog: dict) -> list[dict]:
    """Deferred decisions whose phase has arrived, earliest phase first. A phase arrives
    when the setup step before it is done; pre-launch once setup is complete (launch is
    what's left), post-launch once a release is tagged (`ship` tags v<version>)."""
    try:
        decisions = json.loads((ROOT / "design" / "brief.json").read_text()).get("decisions")
    except (OSError, ValueError, AttributeError):
        return []
    arrived = {
        "shape": True,
        "prototype": prog.get("interview") in DONE,
        "scaffold": prog.get("design") in DONE,
        "first-feature": prog.get("verify") in DONE,
        "pre-launch": prog.get("first_feature") in DONE,
        "post-launch": bool(sh("git", "tag", "--list", "v*")),
    }
    if not isinstance(decisions, list):
        return []
    due = [
        {k: d.get(k) for k in ("id", "question", "ask_at", "why")}
        for d in decisions
        if isinstance(d, dict)
        and d.get("status") == "deferred"
        and arrived.get(str(d.get("ask_at")))
    ]
    return sorted(due, key=lambda d: DECISION_PHASES.index(d["ask_at"]))


def risk_open() -> list[str]:
    """Open risk items, from the same gate `ship` runs (scripts/risk_gate.py), so next and
    ship can't disagree. Empty until the idea has a risk screen; fails open."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("risk_gate", ROOT / "scripts" / "risk_gate.py")
        if spec is None or spec.loader is None:
            return []
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        brief, _ = gate.load_brief(ROOT)
        if not isinstance((brief or {}).get("risk"), dict):
            return []
        return gate.blockers(ROOT, gate.load_categories(None))
    except Exception:
        return []


def local() -> dict:
    box = appbox()
    prog = box["progress"]
    # Same rules as progress.py: a background check that's `running` isn't the next
    # step, and a project set up before the idea check existed isn't sent back to it.
    legacy = prog.get("interview") in DONE and "validate" not in prog
    pending = [
        p for p in SETUP
        if prog.get(p) not in DONE and prog.get(p) != "running" and not (legacy and p == "validate")
    ]
    branch = sh("git", "symbolic-ref", "--short", "HEAD") or "?"
    dirty = sh("git", "status", "--porcelain")
    ahead = sh("git", "rev-list", "--count", "origin/main..HEAD") if branch != "main" else "0"
    return {
        "setup_pending": pending if box["progress"] else [],
        "branch": branch,
        "uncommitted_files": len(dirty.splitlines()) if dirty else 0,
        "commits_ahead_of_main": int(ahead) if ahead and ahead.isdigit() else 0,
        "tracker": box["stack"].get("tracker", "github"),
        "analytics": box["stack"].get("analytics", ""),
        "overdue_rituals": rituals(),
        "decisions_due": decisions_due(prog),
        "risk_open": risk_open(),
        "brief": (ROOT / "docs" / "product" / "BRIEF.md").is_file(),
    }


def remote() -> dict:
    def js(*cmd: str):
        raw = sh(*cmd, timeout=15)
        try:
            return json.loads(raw) if raw else None
        except ValueError:
            return None

    prs = js("gh", "pr", "list", "--state", "open", "--limit", "20",
             "--json", "number,title,isDraft,headRefName,reviewDecision,statusCheckRollup")  # fmt: skip
    for pr in prs or []:
        checks = pr.pop("statusCheckRollup", None) or []
        pr["failing_checks"] = [
            c.get("name") or c.get("context")
            for c in checks
            if (c.get("conclusion") or c.get("state") or "").upper()
            in {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED"}
        ]
    runs = js("gh", "run", "list", "--branch", "main", "--limit", "5",
              "--json", "workflowName,conclusion,url")  # fmt: skip
    issues = js("gh", "issue", "list", "--state", "open", "--limit", "30",
                "--json", "number,title,labels")  # fmt: skip
    for i in issues or []:
        i["labels"] = [lbl.get("name") for lbl in i.get("labels", [])]
    return {
        "gh_available": prs is not None,
        "open_prs": prs or [],
        "main_ci_failing": [r for r in (runs or []) if r.get("conclusion") == "failure"],
        "open_issues": issues or [],
    }


def line(sig: dict) -> str:
    """The single most urgent local signal, as one SessionStart line."""
    if sig["setup_pending"]:
        return (f"setup phase `{sig['setup_pending'][0]}` isn't done: resume it with the "
                "App in a Box `new-app` skill")  # fmt: skip
    if sig["branch"] != "main" and (sig["uncommitted_files"] or sig["commits_ahead_of_main"]):
        return (f"you have work in progress on `{sig['branch']}` "
                f"({sig['uncommitted_files']} uncommitted, {sig['commits_ahead_of_main']} "
                "commits ahead): finish it before starting something new")  # fmt: skip
    overdue = sig["overdue_rituals"]
    if overdue:
        r = max(overdue, key=lambda x: x["days_since"] - x["cadence_days"])
        return f"the `{r['ritual']}` ritual is overdue ({r['days_since']}d, cadence {r['cadence_days']}d)"
    risk = sig.get("risk_open") or []
    if risk:
        return (f"{len(risk)} risk item(s) are open and `ship` will refuse until they're "
                f"answered or accepted, starting with: {risk[0].split(': ')[0].split('. ')[0]}")  # fmt: skip
    due = sig["decisions_due"]
    if due:
        return (f"{len(due)} product decision(s) are due, starting with `{due[0]['id']}` "
                f"(parked until {due[0]['ask_at']})")  # fmt: skip
    return "no local blockers"


def main(argv: list[str]) -> int:
    try:
        sig = local()
        if "--line" in argv:
            print(
                f"- Next: {line(sig)}. Ask for `next` (`/next`, `$next` in Codex) for the full pick."
            )
            return 0
        if "--remote" in argv:
            sig.update(remote())
        print(json.dumps(sig, indent=2))
    except Exception as e:  # never break a session start
        if "--line" not in argv:
            print(json.dumps({"error": str(e)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
