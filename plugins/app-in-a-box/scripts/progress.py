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

# (key, phase number as shown, label, detail). Phase 1 has two steps: shaping the idea
# with the advisor (1a, which keeps the old `interview` key so older setups resume) and
# the idea check (1b), which runs in the background while 1a is still going.
PHASES = [
    ("preflight", "0", "Preflight", "tools installed"),
    ("interview", "1a", "Shape", "your idea in your words: brief + appbox.yaml"),
    ("validate", "1b", "Idea check", "market researched, verdict + VALIDATION.md"),
    ("design", "2", "Prototype", "clicked through, tuned and frozen: tokens + screens"),
    ("accounts", "3", "Accounts", "CLIs logged in"),
    ("scaffold", "4", "Scaffold", "app + backend generated"),
    ("provision", "5", "Provision", "cloud resources + secrets wired"),
    ("harness", "6", "Harness", "guards on and smoke-tested"),
    ("verify", "7", "Verify", "gates green, first PR, first event"),
    ("first_feature", "8", "First feature", "backlog seeded, feature #1 PR"),
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
    done = [k for k, _, _, _ in PHASES if progress.get(k) in DONE]
    # A project set up before the idea check existed has interview done and no
    # validate key: don't send it back to 1a (new-app offers it once instead).
    legacy = progress.get("interview") in DONE and "validate" not in progress
    # A phase that is `running` works in the background (the idea check, started by
    # shape): it isn't what the founder does next, so the one after it is.
    running = [p for p in PHASES if progress.get(p[0]) == "running"]
    nxt = next(
        (
            p
            for p in PHASES
            if progress.get(p[0]) not in DONE
            and progress.get(p[0]) != "running"
            and not (legacy and p[0] == "validate")
        ),
        None,
    )
    title = f"{name}: setup progress" if name else "Setup progress"
    lines = [f"## {title}" if markdown else title, ""]
    for key, num, label, detail in PHASES:
        state = progress.get(key, "")
        if state in DONE:
            mark = "[x]"
        elif nxt and key == nxt[0]:
            mark = "[>]"
        else:
            mark = "[ ]"
        suffix = f" ({state})" if state in ("skipped", "parked", "running", "pending") else ""
        if legacy and key == "validate":
            suffix = " (not run: this project predates it)"
        lines.append(f"{'- ' if markdown else '  '}{mark} {num}. {label}: {detail}{suffix}")
    lines.append("")
    lines.append(f"{len(done)}/{len(PHASES)} steps done.")
    if nxt and progress.get(nxt[0]) == "parked":
        lines.append(f"Parked at phase {nxt[1]}, {nxt[2]}: re-run new-app to pick it back up.")
    elif nxt:
        lines.append(f"Next: phase {nxt[1]}, {nxt[2]}.")
    for p in running:
        lines.append(f"Phase {p[1]}, {p[2]}, is running in the background.")
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
