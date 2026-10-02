#!/usr/bin/env python3
"""Fail on duplicate or malformed Supabase migration versions.

A migration's *version* is the digit prefix before the first `_`, the key the Supabase
CLI writes to `supabase_migrations.schema_migrations`. Two files with one version
collide there: the second silently never applies, or `supabase db reset` dies on the
primary key. (A real app shipped this more than once.) Pick a fresh timestamp instead:
`date -u +%Y%m%d%H%M%S`.

If a collision ever reaches the live database, don't rename the applied file (that
rewrites history); add its exact filename to GRANDFATHERED_DUPLICATES with a comment.

Usage: python3 scripts/check_migration_versions.py [migrations_dir]
Run by .github/workflows/db.yml and scripts/db-test.sh. Standard library only.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

VERSION_RE = re.compile(r"^(\d+)_[A-Za-z0-9_]+\.sql$")
FULL_VERSION_RE = re.compile(r"^\d{14}$")

# version -> exact set of files already sharing it on the live DB (never rename).
GRANDFATHERED_DUPLICATES: dict[str, frozenset[str]] = {}


def check(filenames: list[str]) -> list[str]:
    """One problem string per violation; empty means clean."""
    problems: list[str] = []
    by_version: dict[str, set[str]] = defaultdict(set)
    for name in sorted(filenames):
        if not name.endswith(".sql"):
            continue
        m = VERSION_RE.match(name)
        if not m:
            problems.append(
                f"{name}: not <14 digits>_<name>.sql, so the CLI can't read its version"
            )
            continue
        version = m.group(1)
        if not FULL_VERSION_RE.match(version):
            problems.append(f"{name}: version {version} is not 14 digits (YYYYMMDDHHMMSS)")
        by_version[version].add(name)
    for version, names in sorted(by_version.items()):
        if len(names) < 2:
            continue
        extra = sorted(names - GRANDFATHERED_DUPLICATES.get(version, frozenset()))
        if extra:
            problems.append(
                f"duplicate migration version {version}: {', '.join(sorted(names))}; "
                "give the new file a fresh timestamp"
            )
    return problems


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    directory = Path(argv[1]) if len(argv) > 1 else root / "supabase" / "migrations"
    names = [p.name for p in directory.iterdir() if p.is_file()]
    problems = check(names)
    count = sum(1 for n in names if n.endswith(".sql"))
    if problems:
        for p in problems:
            print(f"::error::{p}")
        print(f"{len(problems)} migration version problem(s) across {count} files", file=sys.stderr)
        return 1
    print(f"OK: {count} migration file(s), no duplicate or malformed versions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
