#!/usr/bin/env python3
"""Accessibility Nutrition Labels, from evidence: docs/product/ACCESSIBILITY.md.

App Store Connect asks, per feature, whether people can complete the app's common
tasks with it: VoiceOver, Voice Control, Larger Text (200% or more), Sufficient
Contrast, Reduced Motion, Dark Interface, Differentiate Without Color Alone, Captions
and Audio Descriptions. This script answers each one from what the repo can prove, and
never from what someone hopes is true. A feature is "supported" only when every piece
of its evidence holds; otherwise it is "not yet claimed" with what is missing.

Evidence it reads (the same checks the gates and CI run):
  - mobile/scripts/check-a11y.js passes (labels, roles, images, text scaling, motion)
  - mobile/__tests__/a11y-screens.test.tsx renders every route at font scale 1 and 2
  - scripts/check_contrast.py passes on design/tokens.json
  - mobile/lib/motion.ts uses useReducedMotion and ReduceMotion.System
  - design/tokens.json has a dark palette; body text scales to 200% (type.*.maxScale)
  - a Maestro flow under mobile/.maestro/ reaches every screen and sheet listed in
    docs/product/SCREENS.md (the app's common tasks)

Only the text between the markers belongs to this script; notes you write around it
are kept:

    <!-- a11y-labels:generated -->  ...  <!-- /a11y-labels:generated -->

    a11y_labels.py            write docs/product/ACCESSIBILITY.md
    a11y_labels.py --check    exit 1 if the answers differ from what the evidence says
    --root PATH               the repo root (default: this script's repo)

Exit codes: 0 ok, 1 drift. Standard library only (node runs check-a11y.js).
Apple's definitions: https://developer.apple.com/help/app-store-connect/manage-app-accessibility/overview-of-accessibility-nutrition-labels/
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_contrast  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = "docs/product/ACCESSIBILITY.md"
GEN = "a11y-labels:generated"
WRITE_CMD = "python3 scripts/a11y_labels.py"
SCREEN_TEST = "mobile/__tests__/a11y-screens.test.tsx"
NO_VIDEO = "not applicable unless the app has video"
VIDEO = re.compile(r"""from\s+["'](expo-video|expo-av)["']|<Video\b""")


@dataclass(frozen=True)
class Facts:
    """What the repo proves, gathered once. Each field is "" when it holds, or why not."""

    lint: str
    screen_test: str
    contrast: str
    motion: str
    dark: str
    large_text: str
    tasks: str
    video: bool


def _read(root: Path, rel: str) -> str:
    p = root / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def lint_fact(root: Path) -> str:
    script = root / "mobile" / "scripts" / "check-a11y.js"
    node = shutil.which("node")
    if not script.is_file():
        return "mobile/scripts/check-a11y.js is missing"
    if not node:
        return "node, to run mobile/scripts/check-a11y.js"
    r = subprocess.run([node, str(script)], capture_output=True, text=True, check=False)
    return "" if r.returncode == 0 else "mobile/scripts/check-a11y.js to pass"


def screen_test_fact(root: Path) -> str:
    src = _read(root, SCREEN_TEST)
    if not src:
        return f"{SCREEN_TEST} (every route rendered and audited)"
    if not re.search(r"describe\.each\(\[\s*1\s*,\s*2\s*\]\)", src):
        return f"{SCREEN_TEST} to run at font scale 1 and 2"
    return ""


def _tokens(root: Path) -> dict:
    try:
        data = json.loads(_read(root, "design/tokens.json") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def contrast_fact(root: Path) -> str:
    tokens = _tokens(root)
    if not tokens:
        return "design/tokens.json"
    errs = check_contrast.check(tokens, check_contrast.text_tokens(root / "design" / "tokens.json"))
    return "scripts/check_contrast.py to pass on design/tokens.json" if errs else ""


def motion_fact(root: Path) -> str:
    src = _read(root, "mobile/lib/motion.ts")
    if "useReducedMotion" in src and "ReduceMotion.System" in src:
        return ""
    return "mobile/lib/motion.ts to honour Reduce Motion (useReducedMotion, ReduceMotion.System)"


def dark_fact(root: Path) -> str:
    tokens = _tokens(root)
    has_dark = "dark" in check_contrast.palettes(tokens) if tokens else False
    return "" if has_dark else "a dark palette in design/tokens.json (color.dark)"


def large_text_fact(root: Path) -> str:
    roles = _tokens(root).get("type") or {}
    short = [r for r in ("body", "secondary") if (roles.get(r) or {}).get("maxScale", 0) < 2]
    if short:
        return "body text that scales to 200% (type." + ", type.".join(short) + ".maxScale >= 2)"
    return ""


def common_tasks(root: Path) -> list[str]:
    """Every screen and sheet docs/product/SCREENS.md lists, as its root testID."""
    text = _read(root, "docs/product/SCREENS.md")
    ids = re.findall(r"^## (Screen|Sheet): .*\(`([^`]+)`\)", text, re.M)
    return [f"{i.replace('_', '-').lower()}-{kind.lower()}" for kind, i in ids]


def tasks_fact(root: Path) -> str:
    tasks = common_tasks(root)
    if not tasks:
        return "docs/product/SCREENS.md, the list of common tasks the prototype freeze writes"
    flows = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((root / "mobile" / ".maestro").rglob("*.y*ml"))
    )
    untested = [
        t for t in tasks if not re.search(rf"^\s*id:\s*[\"']?{re.escape(t)}[\"']?\s*$", flows, re.M)
    ]
    return f"a Maestro flow for {', '.join(untested)}" if untested else ""


def has_video(root: Path) -> bool:
    mobile = root / "mobile"
    for d in ("app", "components", "lib"):
        for p in sorted((mobile / d).rglob("*.ts*")) if (mobile / d).is_dir() else []:
            if "__tests__" not in p.parts and VIDEO.search(p.read_text(encoding="utf-8")):
                return True
    return False


def gather(root: Path) -> Facts:
    return Facts(
        lint=lint_fact(root),
        screen_test=screen_test_fact(root),
        contrast=contrast_fact(root),
        motion=motion_fact(root),
        dark=dark_fact(root),
        large_text=large_text_fact(root),
        tasks=tasks_fact(root),
        video=has_video(root),
    )


# feature -> [(Facts field, what it proves when it holds)], in Apple's order.
EVIDENCE: dict[str, list[tuple[str, str]]] = {
    "VoiceOver": [
        (
            "lint",
            "check-a11y.js: every control has a role and a label, every image labelled or marked decorative",
        ),
        ("screen_test", "a11y-screens.test.tsx: every route's controls are named and reachable"),
        ("tasks", "a Maestro flow for every common task in SCREENS.md"),
    ],
    "Voice Control": [
        ("lint", "check-a11y.js: every control has a name to say, none restating its role"),
        ("screen_test", "a11y-screens.test.tsx: every pressable has a label or visible text"),
        ("tasks", "a Maestro flow for every common task in SCREENS.md"),
    ],
    "Larger Text": [
        ("lint", "check-a11y.js: no allowFontScaling={false}, no font cap under 1.3 in screens"),
        ("large_text", "body and secondary text scale to 200% (design/tokens.json maxScale)"),
        ("screen_test", "a11y-screens.test.tsx: every route renders at font scale 2"),
        ("tasks", "a Maestro flow for every common task in SCREENS.md"),
    ],
    "Sufficient Contrast": [
        ("contrast", "check_contrast.py: every text pair clears WCAG AA in every mode"),
    ],
    "Reduced Motion": [
        (
            "motion",
            "lib/motion.ts: presets carry ReduceMotion.System; loops check useReducedMotion",
        ),
        ("lint", "check-a11y.js: no animation outside lib/motion.ts ignores Reduce Motion"),
    ],
    "Dark Interface": [
        ("dark", "design/tokens.json has a dark palette that check_contrast.py also checks"),
    ],
}
NO_CHECK = {
    "Differentiate Without Color Alone": (
        "a check that no screen carries meaning in colour alone; nothing proves it yet"
    ),
}
VIDEO_ONLY = ("Captions", "Audio Descriptions")


def answer(feature: str, facts: Facts) -> str:
    """One feature's answer: supported only when every piece of evidence holds."""
    if feature in VIDEO_ONLY:
        if not facts.video:
            return f"{NO_VIDEO} (no video player in mobile/)"
        return (
            f"not yet claimed (missing: {feature.lower()} for every video; nothing checks them yet)"
        )
    if feature in NO_CHECK:
        return f"not yet claimed (missing: {NO_CHECK[feature]})"
    pieces = EVIDENCE[feature]
    missing = [getattr(facts, f) for f, _ in pieces if getattr(facts, f)]
    if missing:
        return f"not yet claimed (missing: {'; '.join(dict.fromkeys(missing))})"
    return f"supported (evidence: {'; '.join(why for _, why in pieces)})"


FEATURES = [*EVIDENCE, *NO_CHECK, *VIDEO_ONLY]


def block(facts: Facts) -> str:
    lines = [f"- **{f}**: {answer(f, facts)}" for f in FEATURES]
    return "\n".join([f"<!-- {GEN} -->", *lines, f"<!-- /{GEN} -->"])


def _block_re() -> re.Pattern[str]:
    return re.compile(rf"<!-- {re.escape(GEN)} -->.*?<!-- /{re.escape(GEN)} -->", re.S)


def fresh(facts: Facts) -> str:
    return "\n".join(
        [
            "# Accessibility Nutrition Labels",
            "",
            "<!-- Generated by scripts/a11y_labels.py from what the repo proves. The text",
            "     between the a11y-labels:generated markers is rewritten on every run;",
            "     anything you write outside them is kept. -->",
            "",
            "What to answer in App Store Connect → your app → App Accessibility, one line per",
            "feature. Claim only what says **supported**: each one names the checks behind it,",
            "and the `ship` skill copies these answers and nothing more. Larger Text means",
            "people can finish the common tasks with text at 200% or more.",
            "",
            block(facts),
            "",
            'To claim a feature that says "not yet claimed", make its missing evidence true',
            f"(a check, a flow, a palette), then run `{WRITE_CMD}`.",
            "",
        ]
    )


def update(text: str, facts: Facts) -> str:
    if not text:
        return fresh(facts)
    if _block_re().search(text):
        return _block_re().sub(lambda _m: block(facts), text, count=1)
    return text.rstrip("\n") + "\n\n" + block(facts) + "\n"


def drift(text: str, facts: Facts) -> list[str]:
    found = _block_re().findall(text)
    if not found:
        return [f"{OUT}: the generated block is missing. Run: {WRITE_CMD}"]
    if len(found) > 1:
        return [f"{OUT}: the generated block appears {len(found)} times"]
    if found[0] != block(facts):
        return [f"{OUT}: the answers differ from what the evidence says now. Run: {WRITE_CMD}"]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the answers have drifted")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    out = root / OUT
    facts = gather(root)
    text = out.read_text(encoding="utf-8") if out.is_file() else ""
    if a.check:
        errs = drift(text, facts) if text else [f"{OUT} is missing. Run: {WRITE_CMD}"]
        for e in errs:
            print(e)
        if errs:
            print(
                "accessibility labels check FAILED: never claim a feature the evidence doesn't show."
            )
            return 1
        print(f"{OUT} matches the evidence.")
        return 0
    new = update(text, facts)
    if new != text:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(new, encoding="utf-8")
    print(f"{'wrote' if new != text else 'unchanged:'} {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
