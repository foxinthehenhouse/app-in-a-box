"""docs/slo.yaml: the reliability targets the north-star-report reads every week.

The report can only say "availability is burning its budget" if the file still names
availability, latency and crash-free targets in a shape it can read. A deleted SLO, an
objective of 100% (no budget at all, so every blip is an incident) or a missing unit
turns the weekly reliability line into a guess. Negative controls below.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SLO_FILE = ROOT / "docs" / "slo.yaml"
REQUIRED = {"availability", "latency_p95", "crash_free"}
UNITS = {"percent", "ms"}


def slo_problems(doc: Any) -> list[str]:
    if not isinstance(doc, dict):
        return ["docs/slo.yaml is not a mapping"]
    problems = []
    window = doc.get("window_days")
    if not isinstance(window, int) or not 1 <= window <= 90:
        problems.append(f"window_days must be a whole number of days, 1-90 (got {window!r})")
    slos = doc.get("slos")
    if not isinstance(slos, list) or not slos:
        return [*problems, "no `slos:` list"]
    seen: set[str] = set()
    for i, slo in enumerate(slos):
        if not isinstance(slo, dict):
            problems.append(f"slos[{i}] is not a mapping")
            continue
        sid = slo.get("id")
        label = sid if isinstance(sid, str) and sid else f"slos[{i}]"
        if label in seen:
            problems.append(f"{label}: listed twice")
        seen.add(label)
        for key in ("description", "source"):
            if not isinstance(slo.get(key), str) or not slo[key].strip():
                problems.append(f"{label}: no {key}")
        unit, objective = slo.get("unit"), slo.get("objective")
        if unit not in UNITS:
            problems.append(f"{label}: unit must be one of {sorted(UNITS)} (got {unit!r})")
        if isinstance(objective, bool) or not isinstance(objective, (int, float)):
            problems.append(f"{label}: objective must be a number (got {objective!r})")
        elif unit == "percent" and not 0 < objective < 100:
            problems.append(
                f"{label}: objective {objective}% leaves no error budget; pick below 100"
            )
        elif unit == "ms" and objective <= 0:
            problems.append(f"{label}: objective must be a positive number of ms")
    for missing in sorted(REQUIRED - seen):
        problems.append(f"{missing}: required SLO is missing (the weekly report reads it)")
    return problems


def test_slo_file_is_complete() -> None:
    assert slo_problems(yaml.safe_load(SLO_FILE.read_text())) == []


def test_north_star_report_reads_the_slos() -> None:
    skill = (ROOT / ".agents" / "skills" / "north-star-report" / "SKILL.md").read_text()
    assert "docs/slo.yaml" in skill, "north-star-report no longer reads docs/slo.yaml"


# ---- negative controls ------------------------------------------------------------

GOOD = yaml.safe_load(SLO_FILE.read_text())


def _without(sid: str) -> dict[str, Any]:
    return {**GOOD, "slos": [s for s in GOOD["slos"] if s["id"] != sid]}


def _with(sid: str, **change: Any) -> dict[str, Any]:
    return {**GOOD, "slos": [{**s, **change} if s["id"] == sid else s for s in GOOD["slos"]]}


@pytest.mark.parametrize(
    ("doc", "message"),
    [
        (_without("crash_free"), "crash_free: required SLO is missing"),
        (_with("availability", objective=100), "leaves no error budget"),
        (_with("latency_p95", unit="seconds"), "latency_p95: unit must be one of"),
        (_with("availability", objective="high"), "objective must be a number"),
        (_with("crash_free", source=""), "crash_free: no source"),
        ({**GOOD, "window_days": 365}, "window_days must be"),
        ({**GOOD, "slos": [*GOOD["slos"], GOOD["slos"][0]]}, "availability: listed twice"),
        ({"window_days": 28}, "no `slos:` list"),
    ],
    ids=["missing", "no-budget", "bad-unit", "nan", "no-source", "window", "dupe", "empty"],
)
def test_a_broken_slo_file_is_caught(doc: Any, message: str) -> None:
    found = slo_problems(doc)
    assert any(message in p for p in found), found
