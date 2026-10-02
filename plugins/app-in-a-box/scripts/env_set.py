#!/usr/bin/env python3
"""Upsert KEY=value lines from stdin into a dotenv file, without printing a value.

    <something that prints KEY=value lines> | python3 env_set.py .env

Secrets flow through pipes, never through the agent's transcript: this script
replaces an existing `KEY=` (or `export KEY=`) line or appends a new one, leaves the
file mode 600, and reports only key NAMES. It's the one sanctioned way to write parsed
secrets (e.g. from `supabase projects api-keys -o json`) into .env; the generated
repo's bash-safety hook allows it by name and blocks commands that read .env.

The write is atomic: the new contents go to a 0600 temp file next to the target and
are renamed over it, so a crash mid-write (or a reader racing it) never sees a
truncated or half-written .env, and the file is never world-readable, not even for
the moment between create and chmod.

Standard library only. Exit 0 ok, 1 bad input, 2 usage.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
# `KEY=` or `export KEY=`, as dotenv and shells both accept. Group 1 keeps the prefix.
LINE = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)\s*=")


def parse_line(line: str) -> tuple[str, str] | None:
    """(prefix, KEY) for an assignment line, else None (comments, blanks, junk)."""
    m = LINE.match(line)
    return (m.group(1), m.group(2)) if m else None


def upsert(path: Path, pairs: dict[str, str]) -> list[str]:
    lines = path.read_text().splitlines() if path.exists() else []
    seen: set[str] = set()
    out = []
    for line in lines:
        parsed = parse_line(line)
        name = parsed[1] if parsed else None
        if parsed and name in pairs:
            if name in seen:
                continue  # drop duplicate definitions of a key we're setting
            out.append(f"{parsed[0]}{name}={pairs[name]}")
            seen.add(name)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in pairs.items() if k not in seen]
    # Atomic, 0600 from the first byte: write a private temp file in the same directory
    # (same filesystem, so the rename is atomic) and move it over the target.
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)  # mkstemp already uses 0600; make it explicit for umask-proof reading
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(out) + "\n")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return sorted(pairs)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    pairs: dict[str, str] = {}
    for raw in sys.stdin.read().splitlines():
        if not raw.strip():
            continue
        parsed = parse_line(raw)
        if not parsed:
            print("env_set: expected KEY=value lines on stdin", file=sys.stderr)
            return 1
        k = parsed[1]
        v = raw.split("=", 1)[1]
        if not KEY.match(k) or "\n" in v:
            print(f"env_set: bad key name {k!r}", file=sys.stderr)
            return 1
        pairs[k] = v.strip()
    if not pairs:
        print("env_set: nothing on stdin", file=sys.stderr)
        return 1
    names = upsert(Path(argv[1]), pairs)
    print(f"env_set: wrote {', '.join(names)} to {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
