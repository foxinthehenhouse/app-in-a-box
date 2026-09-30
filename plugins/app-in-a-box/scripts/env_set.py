#!/usr/bin/env python3
"""Upsert KEY=value lines from stdin into a dotenv file, without printing a value.

    <something that prints KEY=value lines> | python3 env_set.py .env

Secrets flow through pipes, never through the agent's transcript: this script
replaces an existing `KEY=` line or appends a new one, keeps the file mode 600,
and reports only key NAMES. It's the one sanctioned way to write parsed secrets
(e.g. from `supabase projects api-keys -o json`) into .env; the generated repo's
bash-safety hook allows it by name and blocks commands that read .env.

Standard library only. Exit 0 ok, 1 bad input, 2 usage.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def upsert(path: Path, pairs: dict[str, str]) -> list[str]:
    lines = path.read_text().splitlines() if path.exists() else []
    seen: set[str] = set()
    out = []
    for line in lines:
        name = line.split("=", 1)[0].strip()
        if name in pairs:
            if name in seen:
                continue  # drop duplicate definitions of a key we're setting
            out.append(f"{name}={pairs[name]}")
            seen.add(name)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in pairs.items() if k not in seen]
    # Create with 0600 from the start: write-then-chmod leaves a new file readable
    # under the default umask for a moment.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(path, 0o600)  # an existing file keeps its old mode through os.open
    return sorted(pairs)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    pairs: dict[str, str] = {}
    for raw in sys.stdin.read().splitlines():
        if not raw.strip():
            continue
        if "=" not in raw:
            print("env_set: expected KEY=value lines on stdin", file=sys.stderr)
            return 1
        k, v = raw.split("=", 1)
        k = k.strip()
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
