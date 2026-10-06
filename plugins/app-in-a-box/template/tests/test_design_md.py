"""DESIGN.md stays a faithful projection of design/tokens.json.

scripts/design_md.py writes the frontmatter and the marked blocks; CI and pre-commit
run its `--check`. These prove the check passes on this repo and FAILS on the two ways
DESIGN.md drifts (a hand edit inside a generated block, a token change nobody
regenerated), and that regenerating keeps the prose people wrote around the blocks.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("design_md", ROOT / "scripts" / "design_md.py")
assert _spec is not None and _spec.loader is not None
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)
TOKENS = json.loads((ROOT / "design" / "tokens.json").read_text())


def test_this_repo_design_md_matches_its_tokens() -> None:
    assert dm.drift((ROOT / "DESIGN.md").read_text(), TOKENS) == []


def test_frontmatter_is_yaml_with_only_stitch_keys() -> None:
    text = dm.fresh(TOKENS)
    data = yaml.safe_load(text.split("---\n")[1])
    assert set(data) <= set(dm.STITCH_KEYS)
    assert data["colors"]["primary"] == TOKENS["color"][TOKENS["mode"]]["accent"]


def test_a_hand_edit_inside_a_generated_block_is_caught() -> None:
    text = dm.fresh(TOKENS).replace("| Primary text |", "| Body copy |")
    assert dm.drift(text, TOKENS) == [
        "DESIGN.md: generated block 'colors' differs from design/tokens.json"
    ]


def test_a_token_change_nobody_regenerated_is_caught() -> None:
    changed = copy.deepcopy(TOKENS)
    changed["radius"]["md"] = 14
    errs = dm.drift(dm.fresh(TOKENS), changed)
    assert "DESIGN.md: frontmatter differs from design/tokens.json" in errs
    assert "DESIGN.md: generated block 'shapes' differs from design/tokens.json" in errs


def test_regeneration_keeps_prose_and_restores_a_deleted_block() -> None:
    mine = "Calm and unhurried: a jar you drop coins into, not a dashboard."
    text = dm.fresh(TOKENS).replace("## Colors\n", f"{mine}\n\n## Colors\n")
    text += "- 2026-10-01: warmer accent, the old one read as an alert.\n"
    close = "<!-- /design.md:generated:motion -->"
    start = text.index("<!-- design.md:generated:motion -->")
    gone = text[:start] + text[text.index(close) + len(close) :]
    assert "generated block 'motion' is missing" in " ".join(dm.drift(gone, TOKENS))
    changed = copy.deepcopy(TOKENS)
    changed["radius"]["md"] = 14
    out = dm.update(gone, changed)
    assert mine in out and "warmer accent" in out
    assert dm.drift(out, changed) == []
    assert out.count("## Motion") == 1
