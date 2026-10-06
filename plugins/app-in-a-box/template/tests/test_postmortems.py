"""Every postmortem links the guard it added (docs/postmortems/*.md).

An incident write-up that ends in "we'll be more careful" changes nothing; the same
failure ships again. So each postmortem's "## Guard added" section must name, as a
backticked repo path, a test, check or alert that exists: `tests/test_x.py`, optionally
`::test_name`, `scripts/check_x.py`, a jest test, a workflow. The template itself is
exempt. Negative controls below.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POSTMORTEMS = ROOT / "docs" / "postmortems"
EXEMPT = {"TEMPLATE.md", "README.md"}
_SECTION = re.compile(r"^## Guard added[ \t]*\n(.*?)(?=^## |\Z)", re.M | re.S)
_PATH = re.compile(r"`([A-Za-z0-9_.][\w./-]*\.\w+)(?:::[\w\[\]-]+)?`")


def postmortem_problems(text: str, root: Path) -> list[str]:
    section = _SECTION.search(text)
    if not section:
        return ['no "## Guard added" section']
    paths = _PATH.findall(section.group(1))
    if not paths:
        return ['"## Guard added" names no guard (a backticked path like `tests/test_x.py`)']
    real = [p for p in paths if (root / p).is_file() and not p.startswith("docs/")]
    if not real:
        return [f'"## Guard added" links {paths}, but none is a guard file in this repo']
    return []


def postmortems(root: Path) -> list[Path]:
    folder = root / "docs" / "postmortems"
    return sorted(p for p in folder.glob("*.md") if p.name not in EXEMPT)


def test_every_postmortem_links_its_guard() -> None:
    # One test over all of them, not a parametrize: a new app has none yet, and an
    # empty parameter set would show up as a skip.
    problems = {
        p.name: found
        for p in postmortems(ROOT)
        if (found := postmortem_problems(p.read_text(encoding="utf-8"), ROOT))
    }
    assert not problems, problems


def test_template_has_the_guard_section() -> None:
    assert "\n## Guard added\n" in (POSTMORTEMS / "TEMPLATE.md").read_text()


# ---- negative controls ------------------------------------------------------------

GOOD = "# Postmortem: x\n\n## Guard added\n\n`tests/test_postmortems.py::test_template_has_the_guard_section`, planted.\n\n## Follow-ups\n"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# Postmortem: x\n\n## Root cause\n\nA typo.\n", 'no "## Guard added" section'),
        ("# P\n\n## Guard added\n\nWe will be more careful.\n\n## Follow-ups\n", "names no guard"),
        ("# P\n\n## Guard added\n\n`tests/test_nope.py`\n", "none is a guard file"),
        ("# P\n\n## Guard added\n\n`docs/slo.yaml`\n", "none is a guard file"),
        (
            "# P\n\n## Guard added\n\nTBD\n\n## Follow-ups\n\n`tests/test_slo.py`\n",
            "names no guard",
        ),
    ],
    ids=["no-section", "no-path", "missing-file", "docs-is-not-a-guard", "path-in-other-section"],
)
def test_a_postmortem_without_a_real_guard_is_caught(text: str, message: str) -> None:
    found = postmortem_problems(text, ROOT)
    assert any(message in p for p in found), found


def test_a_postmortem_with_a_real_guard_passes(tmp_path: Path) -> None:
    assert postmortem_problems(GOOD, ROOT) == []
    (tmp_path / "docs" / "postmortems").mkdir(parents=True)
    (tmp_path / "docs" / "postmortems" / "TEMPLATE.md").write_text("no section")
    (tmp_path / "docs" / "postmortems" / "2026-10-01-x.md").write_text(GOOD)
    assert [p.name for p in postmortems(tmp_path)] == ["2026-10-01-x.md"]
