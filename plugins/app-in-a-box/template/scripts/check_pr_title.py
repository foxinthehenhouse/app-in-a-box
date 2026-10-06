#!/usr/bin/env python3
"""PR title lint. PRs squash-merge, so the title becomes the commit on main: it is what
`git log`, the changelog (ship skill) and every future `git blame` reader sees.

The shape is the backlog skill's: `<type>: <summary> (#42)`, types feat, fix, chore,
docs, refactor. Rules:
  - starts with a known type and `: ` (an optional scope is fine: `fix(auth): ...`)
  - a summary after it, at most 72 characters in all (git's subject line)
  - no WIP / draft / do-not-merge marker: squash-merging one puts it on main for good
  - no trailing full stop
GitHub's own `Revert "..."` titles pass. The ticket id is the `ticket` check's job.

    python3 scripts/check_pr_title.py "feat: streak count on Home (#42)"   exit 0 ok, 1 bad
CI passes the title through the PR_TITLE environment variable instead (never inline in
the shell: a title is untrusted input). Standard library only.
"""

from __future__ import annotations

import os
import re
import sys

TYPES = ("feat", "fix", "chore", "docs", "refactor")
MAX_LEN = 72
SHAPE = re.compile(r"^(?P<type>[a-z]+)(\([a-z0-9-]+\))?!?: (?P<summary>\S.*)$")
# "wip" anywhere, but "draft" only as a marker: `docs: draft the privacy policy` is fine.
WIP = re.compile(r"\bwip\b|\[draft\]|^draft\b|\bdo not merge\b|\bdnm\b", re.I)


def problems(title: str) -> list[str]:
    title = title.strip()
    if title.startswith('Revert "'):
        return []
    found = []
    m = SHAPE.match(title)
    if not m:
        found.append(
            f"title must look like `<type>: <summary>` with type one of {', '.join(TYPES)}"
        )
    elif m.group("type") not in TYPES:
        found.append(f"`{m.group('type')}` is not a type; use one of {', '.join(TYPES)}")
    if len(title) > MAX_LEN:
        found.append(f"title is {len(title)} characters; keep it to {MAX_LEN} (the commit subject)")
    if WIP.search(title):
        found.append("title has a WIP/draft marker; squash merge would put it on main")
    if title.endswith("."):
        found.append("title ends with a full stop")
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    title = args[0] if args else os.environ.get("PR_TITLE", "")
    found = problems(title)
    if found:
        print(f"PR title {title!r}:")
        print(*(f"  - {p}" for p in found), sep="\n")
        print("Example: `feat: streak count on Home (#42)`. Edit the title; the check re-runs.")
        return 1
    print(f"PR title ok: {title!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
