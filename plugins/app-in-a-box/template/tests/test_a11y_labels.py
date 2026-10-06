"""The Accessibility Nutrition Labels are derived from evidence, never hand-claimed.

scripts/a11y_labels.py writes docs/product/ACCESSIBILITY.md; the mobile CI job runs its
`--check`. These prove this repo's file matches its evidence, that each feature drops to
"not yet claimed" the moment one piece of its evidence goes away (one negative control
per piece), and that a hand edit claiming a feature is caught as drift.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("a11y_labels", ROOT / "scripts" / "a11y_labels.py")
assert _spec is not None
assert _spec.loader is not None
al = importlib.util.module_from_spec(_spec)
sys.modules["a11y_labels"] = al  # @dataclass looks its module up while the file runs
_spec.loader.exec_module(al)

ALL_PROVEN = al.Facts(
    lint="", screen_test="", contrast="", motion="", dark="", large_text="", tasks="", video=False
)


def _copy(tmp_path: Path) -> Path:
    """The parts of this repo the evidence reads, copied so a test can break one."""
    for rel in ("scripts", "design", "docs"):
        shutil.copytree(ROOT / rel, tmp_path / rel)
    for rel in ("scripts", "lib", "app", "components", "locales", "__tests__", ".maestro"):
        shutil.copytree(ROOT / "mobile" / rel, tmp_path / "mobile" / rel)
    return tmp_path


def test_this_repo_matches_its_evidence() -> None:
    assert al.main(["--check"]) == 0


def test_supported_only_with_every_piece_of_evidence() -> None:
    for feature in al.EVIDENCE:
        assert al.answer(feature, ALL_PROVEN).startswith("supported (evidence: ")


@pytest.mark.parametrize(
    ("field", "features"),
    [
        ("lint", {"VoiceOver", "Voice Control", "Larger Text", "Reduced Motion"}),
        ("screen_test", {"VoiceOver", "Voice Control", "Larger Text"}),
        ("tasks", {"VoiceOver", "Voice Control", "Larger Text"}),
        ("large_text", {"Larger Text"}),
        ("contrast", {"Sufficient Contrast"}),
        ("motion", {"Reduced Motion"}),
        ("dark", {"Dark Interface"}),
    ],
)
def test_one_missing_piece_unclaims_exactly_its_features(field: str, features: set[str]) -> None:
    facts = dataclasses.replace(ALL_PROVEN, **{field: "the planted gap"})
    unclaimed = {f for f in al.EVIDENCE if not al.answer(f, facts).startswith("supported")}
    assert unclaimed == features
    for f in features:
        assert al.answer(f, facts) == "not yet claimed (missing: the planted gap)"


def test_features_nothing_proves_are_never_claimed() -> None:
    assert al.answer("Differentiate Without Color Alone", ALL_PROVEN).startswith("not yet claimed")
    for f in al.VIDEO_ONLY:
        assert al.answer(f, ALL_PROVEN).startswith("not applicable unless the app has video")
        video = dataclasses.replace(ALL_PROVEN, video=True)
        assert al.answer(f, video).startswith("not yet claimed")
    assert al.FEATURES == [
        "VoiceOver", "Voice Control", "Larger Text", "Sufficient Contrast", "Reduced Motion",
        "Dark Interface", "Differentiate Without Color Alone", "Captions", "Audio Descriptions",
    ]  # fmt: skip


def test_a_hand_claimed_feature_is_drift(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    doc = root / al.OUT
    doc.write_text(
        doc.read_text().replace(
            "- **Differentiate Without Color Alone**: not yet claimed",
            "- **Differentiate Without Color Alone**: supported",
        )
    )
    assert al.main(["--check", "--root", str(root)]) == 1


def test_notes_outside_the_markers_survive_a_rewrite(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    doc = root / al.OUT
    doc.write_text(doc.read_text() + "\nReviewed on a real phone with VoiceOver.\n")
    assert al.main(["--root", str(root)]) == 0
    assert "Reviewed on a real phone with VoiceOver." in doc.read_text()
    assert al.main(["--check", "--root", str(root)]) == 0


@pytest.mark.parametrize(
    ("break_it", "needle"),
    [
        (
            lambda r: (r / "mobile/lib/motion.ts").write_text("export const x = 1;\n"),
            "**Reduced Motion**: not yet",
        ),
        (
            lambda r: (r / "mobile/app/planted.tsx").write_text(
                'import { Pressable } from "react-native";\nexport default () => <Pressable onPress={go} />;\n'
            ),
            "**VoiceOver**: not yet",
        ),
        (lambda r: (r / al.SCREEN_TEST).unlink(), "**Voice Control**: not yet"),
        (
            lambda r: (r / "design/tokens.json").write_text(
                (r / "design/tokens.json").read_text().replace('"maxScale": 2.0', '"maxScale": 1.5')
            ),
            "**Larger Text**: not yet",
        ),
    ],
    ids=["motion-without-reduce-motion", "unlabelled-pressable", "no-screen-test", "body-capped"],
)
def test_real_evidence_going_away_unclaims_and_fails_the_check(
    tmp_path: Path, break_it: Callable[[Path], object], needle: str
) -> None:
    root = _copy(tmp_path)
    break_it(root)
    assert al.main(["--check", "--root", str(root)]) == 1
    al.main(["--root", str(root)])
    assert needle in (root / al.OUT).read_text()


def test_screens_md_tasks_need_a_maestro_flow(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    screens = root / "docs" / "product" / "SCREENS.md"
    screens.write_text("## Screen: Home (`home`)\n\n## Sheet: Edit name (`edit_name`)\n")
    assert al.common_tasks(root) == ["home-screen", "edit-name-sheet"]
    assert al.tasks_fact(root) == ""
    screens.write_text(screens.read_text() + "\n## Screen: Streaks (`streaks`)\n")
    assert al.tasks_fact(root) == "a Maestro flow for streaks-screen"
