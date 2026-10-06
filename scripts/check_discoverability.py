#!/usr/bin/env python3
"""Discoverability check: the kit describes itself one way, everywhere, and its docs link.

People and LLMs find and recommend what is clearly named and well documented. That only
works if every place the kit describes itself says the same thing, and every link in
the docs goes somewhere. Both drift quietly: a manifest gets a new description and the
README keeps the old one; a file moves and llms.txt keeps pointing at it.

    scripts/check_discoverability.py [--root DIR]     the whole repo (default: this one)
    scripts/check_discoverability.py --links FILE...  only: every relative link resolves

Canonical positioning:
    one-liner    .claude-plugin/marketplace.json  metadata.description   (<= 90 chars)
    description  plugins/app-in-a-box/.claude-plugin/plugin.json  description  (<= 300)
Everything else must repeat them exactly (the Codex long description may continue past
the canonical one). Keywords are identical in both plugin manifests and are the GitHub
topics in docs/MAINTAINERS.md. Exit 1 with one line per problem. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ONE_LINER_MAX = 90
DESCRIPTION_MAX = 300
# GitHub topics: lowercase letters, digits and hyphens, at most 50 chars, at most 20.
TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
TOPICS_MAX = 20
# Inline markdown links and images: [text](target) / ![alt](target "title").
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# llmstxt.org: a file-list entry is "- [name](url)" with an optional ": notes".
LLMS_ENTRY_RE = re.compile(r"^- \[[^\]]+\]\([^)\s]+\)(: .+)?$")
GUIDES_DIR = "docs/guides"
QUICKSTART_TARGETS = ("README.md#quickstart", "START_HERE.md")


def slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


def anchors(md: Path) -> set[str]:
    out, in_code = set(), False
    for line in md.read_text().splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code and (m := re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)):
            out.add(slug(m.group(1)))
    return out


def strip_code(text: str) -> str:
    """Drop fenced blocks and inline code: a link shown as code isn't a link."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "", text)


def links(md: Path) -> list[str]:
    return LINK_RE.findall(strip_code(md.read_text()))


def broken_links(md: Path) -> list[str]:
    problems = []
    for target in links(md):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):  # https:, mailto: ...
            continue
        path, _, frag = target.partition("#")
        dest = (md.parent / path).resolve() if path else md
        if not dest.exists():
            problems.append(f"{md.name}: broken link {target} (no such file)")
        elif (
            frag
            and dest.suffix == ".md"
            and dest.is_file()
            and frag not in anchors(dest)
        ):
            problems.append(f"{md.name}: broken link {target} (no heading #{frag})")
    return problems


def load(root: Path, rel: str) -> dict:
    return json.loads((root / rel).read_text())


def check_positioning(root: Path) -> list[str]:
    p: list[str] = []
    market = load(root, ".claude-plugin/marketplace.json")
    claude = load(root, "plugins/app-in-a-box/.claude-plugin/plugin.json")
    codex = load(root, "plugins/app-in-a-box/.codex-plugin/plugin.json")
    one = market.get("metadata", {}).get("description", "")
    desc = claude.get("description", "")
    if not 0 < len(one) <= ONE_LINER_MAX:
        p.append(f"positioning: the one-liner is {len(one)} chars (1-{ONE_LINER_MAX})")
    if not 0 < len(desc) <= DESCRIPTION_MAX:
        p.append(
            f"positioning: the description is {len(desc)} chars (1-{DESCRIPTION_MAX})"
        )
    entry = next(
        (x for x in market.get("plugins", []) if x.get("name") == "app-in-a-box"), {}
    )
    ui = codex.get("interface", {})
    for where, got in (
        (
            "marketplace.json plugins[app-in-a-box].description",
            entry.get("description"),
        ),
        (".codex-plugin/plugin.json description", codex.get("description")),
    ):
        if got != desc:
            p.append(f"positioning: {where} differs from the canonical description")
    if ui.get("shortDescription") != one:
        p.append(
            "positioning: .codex-plugin/plugin.json interface.shortDescription differs from the one-liner"
        )
    if not str(ui.get("longDescription", "")).startswith(desc):
        p.append(
            "positioning: .codex-plugin/plugin.json interface.longDescription doesn't start with the canonical description"
        )
    readme = (root / "README.md").read_text()
    hero = readme.split("\n---", 1)[0]
    if one not in hero or desc not in hero:
        p.append(
            "positioning: the README hero doesn't state the one-liner and the description verbatim"
        )
    llms = root / "llms.txt"
    if llms.is_file():
        quote = " ".join(
            line[1:].strip()
            for line in llms.read_text().splitlines()
            if line.startswith(">")
        )
        if quote != desc:
            p.append(
                "positioning: llms.txt's summary blockquote differs from the canonical description"
            )
    maint = root / "docs/MAINTAINERS.md"
    if maint.is_file() and one not in maint.read_text():
        p.append(
            "positioning: docs/MAINTAINERS.md doesn't give the one-liner as the repo description"
        )
    return p


def check_keywords(root: Path) -> list[str]:
    p: list[str] = []
    claude = load(root, "plugins/app-in-a-box/.claude-plugin/plugin.json").get(
        "keywords", []
    )
    codex = load(root, "plugins/app-in-a-box/.codex-plugin/plugin.json").get(
        "keywords", []
    )
    if claude != codex:
        p.append(
            "keywords: the Claude and Codex plugin manifests list different keywords"
        )
    if len(claude) > TOPICS_MAX or len(set(claude)) != len(claude):
        p.append(
            f"keywords: {len(claude)} keywords; GitHub takes at most {TOPICS_MAX} unique topics"
        )
    for k in claude:
        if not TOPIC_RE.match(k):
            p.append(
                f"keywords: '{k}' isn't a valid GitHub topic (lowercase, digits, hyphens)"
            )
    maint = root / "docs/MAINTAINERS.md"
    if maint.is_file():
        m = re.search(r"<!-- topics -->\s*```\s*\n(.*?)\n```", maint.read_text(), re.S)
        if not m or m.group(1).split() != claude:
            p.append(
                "keywords: docs/MAINTAINERS.md's topics block differs from the manifest keywords"
            )
    return p


def check_version(root: Path) -> list[str]:
    p: list[str] = []
    v = load(root, "plugins/app-in-a-box/.claude-plugin/plugin.json").get("version")
    if load(root, "plugins/app-in-a-box/.codex-plugin/plugin.json").get("version") != v:
        p.append(
            "version: the Claude and Codex plugin manifests state different versions"
        )
    log = root / "CHANGELOG.md"
    released = (
        re.findall(r"^## \[(\d+\.\d+\.\d+)\]", log.read_text(), re.M)
        if log.is_file()
        else []
    )
    if not released or released[0] != v:
        p.append(
            f"version: CHANGELOG.md's newest release isn't the manifest version {v}"
        )
    return p


def check_llms(root: Path) -> list[str]:
    f = root / "llms.txt"
    if not f.is_file():
        return ["llms.txt: missing at the repo root"]
    lines = f.read_text().splitlines()
    p: list[str] = []
    if not lines or not lines[0].startswith("# "):
        p.append("llms.txt: the first line must be the H1 name ('# App in a Box')")
    if not any(line.startswith("> ") for line in lines):
        p.append("llms.txt: no blockquote summary")
    if not any(line.startswith("## ") for line in lines):
        p.append("llms.txt: no '## ' sections of links")
    section = False
    for line in lines:
        if line.startswith("## "):
            section = True
        elif section and line.startswith("-") and not LLMS_ENTRY_RE.match(line):
            p.append(f"llms.txt: not a '- [name](url): note' entry: {line}")
    return p + broken_links(f)


def check_docs(root: Path) -> list[str]:
    p: list[str] = []
    guides = sorted((root / GUIDES_DIR).glob("*.md"))
    if not guides:
        p.append(f"guides: no pages in {GUIDES_DIR}/")
    for g in guides:
        found = links(g)
        if not any(t.endswith(q) for t in found for q in QUICKSTART_TARGETS):
            p.append(f"guides: {g.name} doesn't link to the Quickstart")
        if not any("/skills/" in t for t in found):
            p.append(f"guides: {g.name} doesn't link to a skill")
    for rel in ("README.md", "SHOWCASE.md", "CHANGELOG.md", "docs/MAINTAINERS.md"):
        if not (root / rel).is_file():
            p.append(f"docs: {rel} is missing")
    readme = (root / "README.md").read_text()
    if "SHOWCASE.md" not in readme:
        p.append("docs: the README doesn't link SHOWCASE.md")
    if not (root / ".github/ISSUE_TEMPLATE/show-your-app.yml").is_file():
        p.append("docs: .github/ISSUE_TEMPLATE/show-your-app.yml is missing")
    for md in [
        root / "README.md",
        root / "SHOWCASE.md",
        root / "CHANGELOG.md",
        root / "docs/MAINTAINERS.md",
        *guides,
    ]:
        if md.is_file():
            p += broken_links(md)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--links", nargs="+", metavar="FILE")
    a = ap.parse_args()
    if a.links:
        problems = [x for f in a.links for x in broken_links(Path(f).resolve())]
    else:
        root = Path(a.root).resolve()
        problems = (
            check_positioning(root)
            + check_keywords(root)
            + check_version(root)
            + check_llms(root)
            + check_docs(root)
        )
    for line in problems:
        print(line)
    if problems:
        return 1
    print("discoverability: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
