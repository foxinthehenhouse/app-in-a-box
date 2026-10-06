#!/usr/bin/env python3
"""Fail when the hashed Python lock files have drifted from requirements*.txt.

requirements.txt and requirements-dev.txt say what we ACCEPT (ranges with upper
bounds). The lock files say what we INSTALL: every package, transitive ones too, at
one exact version with its sha256 hashes, so CI and scripts/dev-venv.sh install with
`--require-hashes` and a tampered or swapped upload on PyPI cannot slip in.

    requirements.lock      requirements.txt                       (what ships)
    requirements-dev.lock  requirements.txt + requirements-dev.txt (CI + dev venv)

scripts/lock-deps.sh regenerates both and stamps each with the sha256 of its inputs.
This check fails when:
  - an input changed and its lock was not regenerated (the stamp no longer matches;
    comment-only edits don't count),
  - a requirement is missing from its lock, or a pin is not `==` with a hash,
  - the two locks pin a shared package at different versions (tests must run against
    what ships).

Usage:
    python3 scripts/check_lock.py            # check (CI, .github/workflows/ci.yml)
    python3 scripts/check_lock.py --stamp    # rewrite the stamps (lock-deps.sh does this)
Standard library only, so it runs before anything is installed.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# lock file -> the requirement files it is compiled from, in order.
LOCKS: dict[str, tuple[str, ...]] = {
    "requirements.lock": ("requirements.txt",),
    "requirements-dev.lock": ("requirements.txt", "requirements-dev.txt"),
}
STAMP = "# inputs-sha256: "
FIX = "run scripts/lock-deps.sh and commit the lock files"

_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==([^\s;\\]+)")


def normalize(name: str) -> str:
    """PEP 503: `PyJWT`, `pyjwt` and `py_jwt` are one package."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_lines(text: str) -> list[str]:
    """The lines that change what gets resolved: comments and blanks dropped."""
    out = []
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def inputs_digest(texts: list[str]) -> str:
    joined = "\n".join(ln for t in texts for ln in requirement_lines(t))
    return hashlib.sha256(joined.encode()).hexdigest()


def parse_lock(text: str) -> tuple[str | None, dict[str, str], list[str]]:
    """(stamp, {package: version}, problems) for one lock file."""
    stamp = None
    pins: dict[str, str] = {}
    problems: list[str] = []
    entries: list[list[str]] = []
    for raw in text.splitlines():
        if raw.startswith(STAMP):
            stamp = raw[len(STAMP) :].strip()
        line = raw.split("#", 1)[0].rstrip()  # `# via ...` annotations and the header
        if not line.strip():
            continue
        if line[0].isspace() and entries:
            entries[-1].append(line.strip())  # a continuation: --hash=... lines
        else:
            entries.append([line.strip()])
    for entry in entries:
        head = entry[0].rstrip("\\ ").strip()
        m = _PIN.match(head)
        if not m:
            problems.append(f"not an exact `==` pin: {head}")
            continue
        pins[normalize(m.group(1))] = m.group(3)
        if not any(part.startswith("--hash=sha256:") for part in entry):
            problems.append(f"{head}: no --hash (pip --require-hashes refuses it)")
    return stamp, pins, problems


def check(root: Path) -> list[str]:
    """One problem string per violation; empty means clean."""
    problems: list[str] = []
    all_pins: dict[str, dict[str, str]] = {}
    for lock, inputs in LOCKS.items():
        if not (root / inputs[0]).exists():
            continue  # no Python deps at all (a repo without the backend)
        missing = [p for p in (lock, *inputs) if not (root / p).exists()]
        if missing:
            problems.append(f"{lock}: missing {', '.join(missing)}; {FIX}")
            continue
        texts = [(root / p).read_text(encoding="utf-8") for p in inputs]
        stamp, pins, bad = parse_lock((root / lock).read_text(encoding="utf-8"))
        all_pins[lock] = pins
        problems += [f"{lock}: {b}" for b in bad]
        if stamp is None:
            problems.append(f"{lock}: no `{STAMP.strip()}` line; {FIX}")
        elif stamp != inputs_digest(texts):
            problems.append(
                f"{lock} is stale: {' / '.join(inputs)} changed since it was generated; {FIX}"
            )
        for text in texts:
            for line in requirement_lines(text):
                m = _NAME.match(line)
                if m and normalize(m.group(1)) not in pins:
                    problems.append(f"{lock}: `{line}` is not in the lock; {FIX}")
    if len(all_pins) == 2:
        run, dev = all_pins["requirements.lock"], all_pins["requirements-dev.lock"]
        for name in sorted(run.keys() & dev.keys()):
            if run[name] != dev[name]:
                problems.append(
                    f"{name} is {run[name]} in requirements.lock but {dev[name]} in "
                    f"requirements-dev.lock (CI would test a version that does not ship); {FIX}"
                )
    return problems


def stamp(root: Path) -> None:
    for lock, inputs in LOCKS.items():
        path = root / lock
        if not path.exists():
            continue
        digest = inputs_digest([(root / p).read_text(encoding="utf-8") for p in inputs])
        lines = [
            ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith(STAMP)
        ]
        # After uv's header comment, before the first pin.
        at = next((i for i, ln in enumerate(lines) if not ln.startswith("#")), len(lines))
        lines.insert(at, STAMP + digest)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT
    if "--stamp" in argv:
        stamp(root)
        return 0
    problems = check(root)
    for p in problems:
        print(f"check_lock: {p}")
    if not problems:
        print("check_lock: requirements.lock and requirements-dev.lock match their inputs")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
