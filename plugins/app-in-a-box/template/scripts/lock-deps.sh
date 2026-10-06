#!/usr/bin/env bash
# Regenerate the hashed Python lock files from requirements*.txt.
#
#   scripts/lock-deps.sh                  # after editing requirements.txt / requirements-dev.txt
#   scripts/lock-deps.sh --upgrade        # move every pin to the newest version the ranges allow
#   scripts/lock-deps.sh -P fastapi       # move just one package
#
# Writes requirements.lock (runtime, what ships), requirements-dev.lock (runtime +
# dev tooling, what CI and scripts/dev-venv.sh install) and requirements-semgrep.lock
# (the Semgrep scan, alone: its pins conflict with the API's), every pin with its sha256
# hashes, resolved for Python 3.12 on every platform. Without --upgrade, existing pins
# stay put: only what the edit needs moves. scripts/check_lock.py (in CI) fails when a
# requirements file changes and this wasn't run.
#
# Dependabot bumps requirements*.txt but cannot regenerate these files: on its pip PRs,
# check out the branch, run this, and push the lock files.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v uv >/dev/null 2>&1 || { echo "lock-deps: needs uv (https://docs.astral.sh/uv/getting-started/installation/)" >&2; exit 1; }

COMMON=(--quiet --generate-hashes --universal --python-version 3.12 --custom-compile-command scripts/lock-deps.sh)
uv pip compile "${COMMON[@]}" "$@" requirements.txt -o requirements.lock
# The runtime lock is a constraint here, so the dev lock pins every shared package at
# the version that ships.
uv pip compile "${COMMON[@]}" "$@" requirements.txt requirements-dev.txt -c requirements.lock -o requirements-dev.lock
# Its own environment (CI installs it in the `semgrep` job), so no constraint file.
if [ -f requirements-semgrep.txt ]; then
  uv pip compile "${COMMON[@]}" "$@" requirements-semgrep.txt -o requirements-semgrep.lock
fi
python3 scripts/check_lock.py --stamp
python3 scripts/check_lock.py
