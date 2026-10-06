#!/usr/bin/env bash
# One shared Python 3.12 venv per requirements hash, reused across worktrees.
#
#   scripts/dev-venv.sh                        # create/reuse; prints the venv path
#   scripts/dev-venv.sh python -m pytest -q    # run a command inside it
#
# Lives outside the repo (~/.cache/__APP_SLUG__) so new worktrees reuse it
# instantly; ./.venv is a gitignored symlink to it. Uses uv if installed.
# Installs requirements-dev.lock (runtime + pytest, ruff, pyright, pyyaml..., every
# package at an exact version with its hashes) with --require-hashes, the same file
# CI installs. Edited requirements*.txt? Re-lock first (the command heads each .lock).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQ="$ROOT/requirements.txt"
DEV_REQ="$ROOT/requirements-dev.txt"
LOCK="$ROOT/requirements-dev.lock"
# Fallback for a repo that predates requirements-dev.txt.
DEV_DEPS="pytest pytest-asyncio ruff black"

hash_cmd() { if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi; }
if [ -f "$LOCK" ]; then
  INSTALL_ARGS=(--require-hashes -r "$LOCK")
  KEY="$(hash_cmd <"$LOCK" | cut -c1-12)"
elif [ -f "$DEV_REQ" ]; then
  DEV_ARGS=(-r "$DEV_REQ")
  KEY="$( { cat "$REQ" "$DEV_REQ"; } | hash_cmd | cut -c1-12)"
else
  read -r -a DEV_ARGS <<<"$DEV_DEPS"
  KEY="$( { cat "$REQ"; echo "$DEV_DEPS"; } | hash_cmd | cut -c1-12)"
fi
# A repo that predates the lock installs the ranges, unhashed.
[ -n "${INSTALL_ARGS+x}" ] || INSTALL_ARGS=(-r "$REQ" "${DEV_ARGS[@]}")
VENV="${APP_VENV_HOME:-$HOME/.cache/__APP_SLUG__}/venv-py312-$KEY"

if [ ! -f "$VENV/.ready" ]; then
  mkdir -p "$(dirname "$VENV")"
  echo "dev-venv: building $VENV" >&2
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 "$VENV" >&2
    uv pip install --python "$VENV/bin/python" "${INSTALL_ARGS[@]}" >&2
  else
    PY=""
    for c in python3.12 python3.13 python3; do
      if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then PY="$c"; break; fi
    done
    [ -n "$PY" ] || { echo "dev-venv: need Python 3.12+ (or install uv)" >&2; exit 1; }
    "$PY" -m venv "$VENV"
    "$VENV/bin/pip" install -q "${INSTALL_ARGS[@]}" >&2
  fi
  touch "$VENV/.ready"
fi
ln -sfn "$VENV" "$ROOT/.venv"

if [ "$#" -eq 0 ]; then echo "$VENV"; exit 0; fi
cd "$ROOT"
PATH="$VENV/bin:$PATH" exec "$@"
