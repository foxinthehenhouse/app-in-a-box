#!/usr/bin/env python3
"""Render App in a Box setup progress from appbox.yaml as a checklist.

    progress.py [path/to/appbox.yaml] [--markdown]

The new-app orchestrator prints this after every phase so the person always sees
where they are, what's done and what's next. Standard library only (no PyYAML):
it reads just the flat `progress:` mapping and `app.name`.
"""

from __future__ import annotations

import sys
from pathlib import Path

PHASES = [
    ("preflight", "Preflight", "tools installed"),
    ("interview", "Interview", "brief + appbox.yaml"),
    ("design", "Design", "direction picked, tokens written"),
    ("accounts", "Accounts", "CLIs logged in"),
    ("scaffold", "Scaffold", "app + backend generated"),
    ("provision", "Provision", "cloud resources + secrets wired"),
    ("harness", "Harness", "guards on and smoke-tested"),
    ("verify", "Verify", "gates green, first PR, first event"),
    ("first_feature", "First feature", "backlog seeded, feature #1 PR"),
]
DONE = {"done", "true", "yes", "skipped"}


def read_progress(text: str) -> tuple[str, dict[str, str]]:
    name, progress, section = "", {}, None
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        value = value.strip().strip("\"'")
        if indent == 0:
            section = key
        elif section == "app" and indent == 2 and key == "name":
            name = value
        elif section == "progress" and indent == 2:
            progress[key] = value.lower()
    return name, progress


def render(text: str, markdown: bool = False) -> str:
    name, progress = read_progress(text)
    done = [k for k, _, _ in PHASES if progress.get(k) in DONE]
    nxt = next((p for p in PHASES if progress.get(p[0]) not in DONE), None)
    title = f"{name}: setup progress" if name else "Setup progress"
    lines = [f"## {title}" if markdown else title, ""]
    for i, (key, label, detail) in enumerate(PHASES):
        state = progress.get(key, "")
        if state in DONE:
            mark = "[x]"
        elif nxt and key == nxt[0]:
            mark = "[>]"
        else:
            mark = "[ ]"
        suffix = " (skipped)" if state == "skipped" else ""
        lines.append(f"{'- ' if markdown else '  '}{mark} {i}. {label}: {detail}{suffix}")
    lines.append("")
    lines.append(f"{len(done)}/{len(PHASES)} phases done.")
    if nxt:
        lines.append(f"Next: phase {PHASES.index(nxt)}, {nxt[1]}.")
    else:
        lines.append("Setup complete. From here, the `next` skill picks what to do.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    path = Path(args[0] if args else "appbox.yaml")
    if not path.is_file():
        print(f"No {path} yet: setup hasn't started. Phase 0 (Preflight) is next.")
        return 0
    print(render(path.read_text(), markdown="--markdown" in argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
