#!/usr/bin/env bash
# Local API on :8000 with reload. Works from any checkout or worktree.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$("$ROOT/scripts/dev-venv.sh")/bin/python"
cd "$ROOT"
PYTHONPATH="$ROOT" exec "$PY" -m uvicorn backend.main:create_app --factory --reload --port "${PORT:-8000}"
