"""The launch gate (scripts/risk_gate.py) holds while a risk item is open.

`ship` runs `python3 scripts/risk_gate.py check` before anything else. These prove the
gate passes a screened idea with every item answered or accepted, and FAILS, naming the
item, on each way it can be open: an unanswered question, an accepted risk with no owner
or date, a high-tier category with nothing resolved, and a feature that touched a
category the screen never covered. The categories here are a two-entry stand-in for the
kit's scripts/risk/categories.json, built inline so no fake data file ships in the app.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("risk_gate", ROOT / "scripts" / "risk_gate.py")
assert _spec is not None and _spec.loader is not None
rg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rg)

CATEGORIES = {
    "location": {
        "id": "location",
        "tier_floor": "elevated",
        "triggers": ["map", "gps"],
        "questions": [{"id": "location.consent", "text": "Who agrees to share it?"}],
    },
    "minors": {
        "id": "minors",
        "tier_floor": "high",
        "triggers": ["kids"],
        "questions": [{"id": "minors.consent", "text": "How does a parent consent?"}],
    },
}


def write_app(tmp: Path, risk: dict | None) -> Path:
    (tmp / "design").mkdir(parents=True, exist_ok=True)
    brief: dict = {"decisions": []}
    if risk is not None:
        brief["risk"] = risk
    (tmp / "design" / "brief.json").write_text(json.dumps(brief))
    return tmp


def screened(**overrides: object) -> dict:
    risk = {
        "tier": "high",
        "categories": [{"id": "minors", "why": "a kids app", "source": "inferred"}],
        "questions": [
            {"id": "minors.consent", "category": "minors", "status": "asked", "answer": "VPC"}
        ],
        "abuse_cases": [],
        "accepted": [],
        "screened_at": "shape",
        "declined": [],
    }
    risk.update(overrides)
    return risk


def test_a_screened_idea_with_everything_answered_passes(tmp_path: Path) -> None:
    assert rg.blockers(write_app(tmp_path, screened()), CATEGORIES) == []


def test_an_unscreened_idea_is_blocked(tmp_path: Path) -> None:
    [only] = rg.blockers(write_app(tmp_path, None), CATEGORIES)
    assert "never risk-screened" in only


def test_an_open_question_blocks_and_is_named(tmp_path: Path) -> None:
    q = {"id": "minors.consent", "category": "minors", "status": "deferred", "answer": None}
    found = rg.blockers(write_app(tmp_path, screened(questions=[q])), CATEGORIES)
    assert any("open question `minors.consent`" in f and "parent consent" in f for f in found)
    assert any("high-tier category `minors`" in f for f in found)


@pytest.mark.parametrize(
    ("entry", "says"),
    [
        ({"item": "minors.consent", "on": "2026-10-06"}, "no owner (`by`)"),
        ({"item": "minors.consent", "by": "owner"}, "no date (`on`"),
        ({"item": "minors.consent", "by": "owner", "on": "soon"}, "no date (`on`"),
    ],
)
def test_an_accepted_risk_without_owner_or_date_is_rejected(
    tmp_path: Path, entry: dict, says: str
) -> None:
    q = {"id": "minors.consent", "category": "minors", "status": "open", "answer": None}
    found = rg.blockers(write_app(tmp_path, screened(questions=[q], accepted=[entry])), CATEGORIES)
    assert any("accepted risk `minors.consent` is rejected" in f and says in f for f in found)
    assert any("open question `minors.consent`" in f for f in found)  # and it doesn't resolve


def test_a_valid_accepted_risk_resolves_its_question(tmp_path: Path) -> None:
    q = {"id": "minors.consent", "category": "minors", "status": "open", "answer": None}
    ok = {"item": "minors.consent", "by": "owner", "on": "2026-10-06", "note": "beta only"}
    assert (
        rg.blockers(write_app(tmp_path, screened(questions=[q], accepted=[ok])), CATEGORIES) == []
    )


def test_screens_md_naming_an_unscreened_category_blocks(tmp_path: Path) -> None:
    app = write_app(tmp_path, screened())
    (app / "docs" / "product").mkdir(parents=True)
    (app / "docs" / "product" / "SCREENS.md").write_text("## Screen: Map\nA live map.\n")
    found = rg.blockers(app, CATEGORIES)
    assert any("SCREENS.md mentions `location` ('map')" in f for f in found)
    # "roadmap" is not "map": trigger words match whole words only
    (app / "docs" / "product" / "SCREENS.md").write_text("## Screen: Roadmap\n")
    assert rg.blockers(app, CATEGORIES) == []


def test_rescreen_adds_the_category_opens_its_questions_and_raises_the_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPBOX_RISK_SCREEN", "none")
    app = write_app(tmp_path, screened(tier="standard", categories=[], questions=[]))
    cats = tmp_path / "cats.json"
    cats.write_text(json.dumps({"categories": list(CATEGORIES.values())}))
    argv = ["rescreen", "--app", str(app), "--categories", str(cats)]
    assert rg.main([*argv, "--text", "see friends on a map", "--check"]) == 1
    assert rg.main([*argv, "--text", "see friends on a map"]) == 0
    risk = json.loads((app / "design" / "brief.json").read_text())["risk"]
    assert risk["tier"] == "elevated"
    assert [c["id"] for c in risk["categories"]] == ["location"]
    assert risk["questions"][0]["id"] == "location.consent"
    assert any("open question `location.consent`" in f for f in rg.blockers(app, CATEGORIES))


def test_combinations_raise_one_tier_but_never_to_stop() -> None:
    cats = dict(CATEGORIES, ugc={"id": "ugc", "tier_floor": "elevated"})
    assert rg.computed_tier(["location", "ugc"], cats) == "elevated"
    assert rg.computed_tier(["location"], {"location": {"tier_floor": "standard"}}) == "standard"
    lo = {"minors": {"tier_floor": "elevated"}, "location": {"tier_floor": "elevated"}}
    assert rg.computed_tier(["minors", "location"], lo) == "high"
    assert rg.computed_tier(["minors", "location"], CATEGORIES) == "high"


def test_the_checklist_says_talk_to_counsel_at_high_and_never_claims_compliance(
    tmp_path: Path,
) -> None:
    app = write_app(tmp_path, screened())
    text = rg.render_checklist(app, screened(), CATEGORIES, "")
    assert "Talk to counsel before launch" in text
    assert "is not a statement that the app complies" in text
    assert "is compliant" not in text.lower()
    low = rg.render_checklist(app, screened(tier="elevated"), CATEGORIES, "")
    assert "Talk to counsel" not in low


def test_ticks_and_owner_notes_survive_a_regeneration(tmp_path: Path) -> None:
    app = write_app(tmp_path, screened())
    first = rg.render_checklist(app, screened(), CATEGORIES, "")
    line = next(ln for ln in first.splitlines() if ln.startswith("- [ ] A privacy policy URL"))
    edited = first.replace(line, "- [x]" + line[5:]) + "\nMy own note.\n"
    again = rg.render_checklist(app, screened(), CATEGORIES, edited)
    assert "- [x] A privacy policy URL" in again and "My own note." in again
    assert again == edited
