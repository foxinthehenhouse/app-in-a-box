#!/usr/bin/env python3
"""SPEND LEDGER: token accounting per day / session / subagent type / model.

The rest of the loop reads corrections, failures and usage but never cost, so
"that delegation was expensive" has no number behind it. This adds one.

Adapted from two sources:
  - paperclipai/paperclip (MIT): a budget per agent. Here it is SOFT: the
    healthcheck nudges and never blocks, so nobody is locked out mid-fix.
  - ryoppippi/ccusage (MIT): usage from the agent's local transcripts,
    deduplicated by (message.id, requestId). Claude Code writes one JSONL line
    per content block and each repeats the message's usage, so a naive sum
    double- or triple-counts.

Unit: INPUT-TOKEN EQUIVALENTS (ITE) = input + 1.25x cache write + 0.1x cache read
+ 5x output (Anthropic list-price ratios relative to base input). Relative cost
without a price table that goes stale, and not a bill (you may be on a plan).

Claude Code transcripts only. Codex rollouts are NOT counted: their token-usage
records are cumulative per session and not documented as a stable format, and
a ledger that guesses is worse than one that says what it skipped.

    python3 .claude/hooks/spend_ledger.py                  # last 7 days, by day
    python3 .claude/hooks/spend_ledger.py --days 30 --by agent
    python3 .claude/hooks/spend_ledger.py --output json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
WEIGHTS = {"input": 1.0, "cache_write": 1.25, "cache_read": 0.1, "output": 5.0}
FIELDS = {
    "input": "input_tokens",
    "cache_write": "cache_creation_input_tokens",
    "cache_read": "cache_read_input_tokens",
    "output": "output_tokens",
}


def ite(u: dict) -> float:
    return sum(u.get(k, 0) * w for k, w in WEIGHTS.items())


def _lines(path: Path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    yield d
    except OSError:
        return


def _agent_types(parent: Path) -> dict[str, str]:
    """agentId -> subagent_type, from the parent transcript's Agent tool calls."""
    by_tool_use, out = {}, {}
    for d in _lines(parent):
        msg = d.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                inp = block.get("input") or {}
                by_tool_use[block.get("id")] = inp.get("subagent_type") or "general-purpose"
            elif block.get("type") == "tool_result":
                res = d.get("toolUseResult")
                agent_id = res.get("agentId") if isinstance(res, dict) else None
                if agent_id and block.get("tool_use_id") in by_tool_use:
                    out[str(agent_id)] = by_tool_use[block["tool_use_id"]]
    return out


def transcript_files(dirs, since_ts: float):
    """(path, owning parent transcript or None) for every transcript touched since since_ts."""
    for d in dirs:
        base = Path(d)
        if not base.is_dir():
            continue
        for p in base.glob("*.jsonl"):
            if p.stat().st_mtime >= since_ts:
                yield p, None
        for p in base.glob("*/subagents/*.jsonl"):
            if p.stat().st_mtime >= since_ts:
                yield p, base / (p.parent.parent.name + ".jsonl")


def collect(dirs, days: int = 7, now: dt.datetime | None = None) -> list[dict]:
    """One row per deduplicated assistant message inside the window."""
    now = now or dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=days)
    rows, seen = [], set()
    type_cache: dict[Path, dict[str, str]] = {}
    for path, parent in transcript_files(dirs, since.timestamp() - 86400):
        agent = "main"
        if parent is not None:
            if parent not in type_cache:
                type_cache[parent] = _agent_types(parent) if parent.exists() else {}
            agent = type_cache[parent].get(path.stem.removeprefix("agent-"), "subagent:unknown")
        for d in _lines(path):
            if d.get("type") != "assistant":
                continue
            msg = d.get("message") or {}
            usage = msg.get("usage") if isinstance(msg, dict) else None
            if not isinstance(usage, dict):
                continue
            key = (msg.get("id"), d.get("requestId"))
            if key != (None, None):
                if key in seen:
                    continue
                seen.add(key)
            try:
                ts = dt.datetime.fromisoformat(str(d.get("timestamp", "")).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue
            if ts < since:
                continue
            row_agent = "subagent:inline" if agent == "main" and d.get("isSidechain") else agent
            u = {k: int(usage.get(src) or 0) for k, src in FIELDS.items()}
            rows.append(
                {
                    "day": ts.astimezone().date().isoformat(),
                    "session": str(d.get("sessionId") or path.stem)[:8],
                    "agent": row_agent,
                    "model": str(msg.get("model") or "unknown"),
                    **u,
                    "ite": ite(u),
                }
            )
    return rows


def summarise(rows, by: str) -> list[dict]:
    agg: dict[str, dict] = defaultdict(
        lambda: {**{k: 0 for k in FIELDS}, "ite": 0.0, "messages": 0}
    )
    for r in rows:
        a = agg[r[by]]
        for k in FIELDS:
            a[k] += r[k]
        a["ite"] += r["ite"]
        a["messages"] += 1
    return sorted(({by: k, **v} for k, v in agg.items()), key=lambda x: -x["ite"])


def weekly_budget_nudge(manifest: dict, dirs) -> str | None:
    """Healthcheck hook: a nudge when the trailing 7 days exceed the soft budget.

    Inert until manifest.spend_budget.weekly_ite is set (null by default).
    Never raises: a meter must not break SessionStart."""
    try:
        budget = (manifest.get("spend_budget") or {}).get("weekly_ite")
        if not budget:
            return None
        rows = collect(dirs, 7)
        total = sum(r["ite"] for r in rows)
        if total <= budget:
            return None
        top = summarise(rows, "agent")[:3]
        where = ", ".join(f"{t['agent']} {t['ite'] / 1e6:.1f}M" for t in top)
        return (
            f"Spend over soft budget: {total / 1e6:.1f}M ITE in 7d vs {budget / 1e6:.1f}M"
            + (f" (top: {where})" if where else "")
            + ". Run `python3 .claude/hooks/spend_ledger.py --by agent` and let the "
            "harness-optimize skill treat the heaviest line as a pruning signal. Nothing is blocked."
        )
    except Exception:
        return None


def _fmt(n: float) -> str:
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.1f}K" if n >= 1e3 else f"{n:.0f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--by", choices=["day", "session", "agent", "model"], default="day")
    ap.add_argument("--output", choices=["text", "json"], default="text")
    ap.add_argument("--dir", action="append", help="transcript dir override (repeatable; tests)")
    args = ap.parse_args()

    if args.dir:
        dirs = args.dir
    else:
        sys.path.insert(0, str(HOOK_DIR))
        from harness_paths import claude_transcript_dirs

        dirs = claude_transcript_dirs(
            os.environ.get("CLAUDE_PROJECT_DIR") or str(HOOK_DIR.parents[1])
        )
    rows = collect(dirs, args.days)
    if not rows:
        print(
            f"REFUSING: no assistant usage in {args.days}d across {len(dirs)} Claude transcript "
            "dir(s). Zero means the transcript source is disconnected (or no Claude Code "
            "sessions yet; Codex usage is not counted), not that nothing was spent.",
            file=sys.stderr,
        )
        return 2
    table = summarise(rows, args.by)
    if args.output == "json":
        print(
            json.dumps(
                {"days": args.days, "by": args.by, "weights": WEIGHTS, "rows": table}, indent=2
            )
        )
        return 0
    total = sum(r["ite"] for r in rows)
    print(
        f"Spend ledger: last {args.days}d, by {args.by} · {len(rows)} messages · "
        f"{_fmt(total)} ITE (input-token equivalents; not a bill)"
    )
    print(
        f"  {args.by:<28} {'ITE':>9} {'share':>6} {'output':>9} {'cache_rd':>9} {'cache_wr':>9} {'msgs':>6}"
    )
    for r in table:
        print(
            f"  {str(r[args.by])[:28]:<28} {_fmt(r['ite']):>9} {r['ite'] / total:>6.0%} "
            f"{_fmt(r['output']):>9} {_fmt(r['cache_read']):>9} {_fmt(r['cache_write']):>9} {r['messages']:>6}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
