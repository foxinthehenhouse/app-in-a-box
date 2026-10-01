"""AGENTS.md stays true to the code (the "living AGENTS.md").

AGENTS.md is the first thing every agent reads, so a stale one misleads every session.
It rots in two quiet ways, and this test catches both:
  - **Unfilled setup markers.** The scaffold phase fills the `<!-- appbox:... -->`
    markers (product, critical rules, AI fence, voice, domain rules). Once
    `appbox.yaml` says scaffolding is done, any marker left is a hole in the context.
  - **A map that no longer matches the tree.** `## Where things live` must name every
    screen (mobile/app route files), API router, service module and database table.
    Add a feature without its row and CI fails, so the map is updated in the same PR.
Dead path references are test_context_docs.py's job. Each check has a negative control.
"""

from __future__ import annotations

import re
from pathlib import Path

from harness_lib import ROOT

AGENTS = ROOT / "AGENTS.md"
MARKER = re.compile(r"<!--\s*appbox:([a-z-]+)")
TABLE = re.compile(
    r'create\s+table\s+(?:if\s+not\s+exists\s+)?(?:"?public"?\.)?"?([A-Za-z_][A-Za-z0-9_]*)"?',
    re.I,
)
SQL_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def scaffold_done(root: Path) -> bool:
    box = root / "appbox.yaml"
    if not box.is_file():
        return False
    return bool(re.search(r"^\s+scaffold:\s*(done|true|yes)\b", box.read_text(), re.M))


def unfilled_markers(root: Path) -> list[str]:
    """`<!-- appbox:x -->` markers left in any AGENTS.md after the scaffold phase."""
    if not scaffold_done(root):
        return []  # a pristine template: the markers are the scaffold's to-do list
    left = []
    for doc in sorted(root.glob("**/AGENTS.md")):
        if "node_modules" in doc.parts:
            continue
        for name in MARKER.findall(doc.read_text(encoding="utf-8")):
            left.append(f"{doc.relative_to(root)}: appbox:{name}")
    return left


def expected_entries(root: Path) -> dict[str, str]:
    """What the map must mention -> why (what kind of thing it is)."""
    want: dict[str, str] = {}
    app = root / "mobile" / "app"
    for f in sorted(app.rglob("*.tsx")) if app.is_dir() else []:
        rel = f.relative_to(root / "mobile").as_posix()
        if f.name.startswith(("_", "+")) or "__tests__" in f.parts:
            continue  # layouts and special routes aren't screens
        want[rel] = "screen"
    for f in sorted((root / "backend" / "routers").glob("*.py")):
        if f.name != "__init__.py":
            want[f"routers/{f.name}"] = "API router"
    for f in sorted((root / "backend" / "services").glob("*.py")):
        if f.name != "__init__.py":
            want[f"services/{f.name}"] = "service module"
    for sql in sorted((root / "supabase" / "migrations").glob("*.sql")):
        for table in TABLE.findall(SQL_COMMENTS.sub("", sql.read_text(encoding="utf-8"))):
            want[f"`{table.lower()}`"] = "table"
    return want


def missing_from_map(root: Path) -> list[str]:
    where = section(AGENTS_TEXT(root), "Where things live")
    if not where.strip():
        return ["AGENTS.md has no '## Where things live' section"]
    return [
        f"{kind} {entry}" for entry, kind in expected_entries(root).items() if entry not in where
    ]


def AGENTS_TEXT(root: Path) -> str:  # noqa: N802 (reads like the file it returns)
    return (root / "AGENTS.md").read_text(encoding="utf-8")


def test_no_setup_markers_left_after_scaffold() -> None:
    left = unfilled_markers(ROOT)
    assert not left, (
        "AGENTS.md still has unfilled setup markers (fill them from docs/product/BRIEF.md, "
        "then delete the marker comment): " + ", ".join(left)
    )


def test_where_things_live_covers_the_tree() -> None:
    missing = missing_from_map(ROOT)
    assert not missing, (
        "AGENTS.md → '## Where things live' is missing: "
        + ", ".join(missing)
        + ". Add a row (or extend one) in the same PR as the code."
    )


# Negative controls.
def _mini(tmp: Path, agents: str, scaffold: str | None) -> Path:
    (tmp / "backend" / "routers").mkdir(parents=True)
    (tmp / "backend" / "routers" / "plants.py").write_text("")
    (tmp / "mobile" / "app" / "(app)").mkdir(parents=True)
    (tmp / "mobile" / "app" / "(app)" / "plants.tsx").write_text("")
    (tmp / "mobile" / "app" / "(app)" / "_layout.tsx").write_text("")
    (tmp / "supabase" / "migrations").mkdir(parents=True)
    (tmp / "supabase" / "migrations" / "1_p.sql").write_text(
        "create table if not exists public.plants (id int);\n"
        "-- create table old_idea (x int);\n"
        'create table "public"."Pots" (id int);\n'
    )
    (tmp / "AGENTS.md").write_text(agents)
    if scaffold:
        (tmp / "appbox.yaml").write_text(f"progress:\n  scaffold: {scaffold}\n")
    return tmp


def test_new_router_screen_or_table_without_a_row_fails(tmp_path: Path) -> None:
    root = _mini(tmp_path, "# X\n\n## Where things live\n\n| Area |\n", None)
    assert missing_from_map(root) == [
        "screen app/(app)/plants.tsx",
        "API router routers/plants.py",
        "table `plants`",
        "table `pots`",
    ]
    (root / "AGENTS.md").write_text(
        "## Where things live\n| Plants | `app/(app)/plants.tsx` | `routers/plants.py` | | `plants`, `pots` |\n"
    )
    assert missing_from_map(root) == []


def test_markers_only_fail_once_scaffold_is_done(tmp_path: Path) -> None:
    root = _mini(tmp_path, "# X\n<!-- appbox:voice: fill me -->\n", None)
    assert unfilled_markers(root) == []
    (root / "appbox.yaml").write_text("progress:\n  scaffold: done\n")
    assert unfilled_markers(root) == ["AGENTS.md: appbox:voice"]
