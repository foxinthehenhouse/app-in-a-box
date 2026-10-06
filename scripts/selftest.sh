#!/usr/bin/env bash
# App in a Box self-test. Renders the template into a temp dir and proves it works:
#   - renderer: placeholders replaced, adapters generated, TOML/JSON valid
#   - design: default tokens pass the contrast check
#   - backend: pytest green, AND the ownership test fails when scoping is removed
#   - guards: git hooks refuse commit-on-main, staged .env, key-shaped strings;
#             Claude hooks inject path rules and block push-to-main
#   - mobile (--mobile, needs npm registry + ~3 min): real create-expo-app + overlay,
#             `npm run gates` green, and each mobile guard fails on a planted violation
#
#   scripts/selftest.sh [--mobile] [--keep]
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(cd "$HERE/../plugins/app-in-a-box" && pwd)"
MOBILE=0; KEEP=0
for a in "$@"; do case "$a" in --mobile) MOBILE=1 ;; --keep) KEEP=1 ;; esac; done
# The selftest reads the generated workflows as YAML. Say so up front rather than
# failing two checks with a swallowed ImportError.
T="$(mktemp -d)"; [ "$KEEP" = 1 ] || trap 'rm -rf "$T"' EXIT
# Interpreter. Every check calls bare `python3`, and they need Python >= 3.11 (tomllib
# parses the Codex adapters) with PyYAML (the generated workflows are read as YAML).
# macOS ships `python3` = 3.9, so the first run on a Mac used to fail three checks with
# a swallowed ModuleNotFoundError and no hint. Pick the interpreter up front: $PYTHON
# if set, else the first qualifying python3 / python3.13 / python3.12 / python3.11 on
# PATH, and put it first on PATH as `python3` so every check and sourced area uses it.
_py_ok() { "$1" -c 'import sys, tomllib, yaml; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }
PY_BIN=""
for c in ${PYTHON:-} python3 python3.13 python3.12 python3.11; do
  [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && _py_ok "$c" && { PY_BIN="$(command -v "$c")"; break; }
done
if [ -z "$PY_BIN" ]; then
  echo "selftest: needs Python >= 3.11 with PyYAML. Found: $(python3 --version 2>&1 || echo 'no python3')."
  echo "          Install one (brew install python@3.12; python3.12 -m pip install pyyaml) or run PYTHON=/path/to/python3.12 $0"
  exit 2
fi
# A wrapper script, not a symlink: a symlink named python3 makes CPython look for
# pyvenv.cfg beside the LINK, so a venv interpreter would silently run as its base.
mkdir -p "$T/bin" && printf '#!/bin/sh\nexec "%s" "$@"\n' "$PY_BIN" > "$T/bin/python3" && chmod +x "$T/bin/python3" && export PATH="$T/bin:$PATH"
echo "python3: $PY_BIN ($(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))"
PASS=0; FAIL=0; SKIP=0
ok()  { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }
# skip <check> <what's missing>: a check that couldn't run is never silent. Under
# APPBOX_SELFTEST_STRICT=1 (kit CI) it is a failure, so CI can't go green by skipping.
skip() {
  if [ "${APPBOX_SELFTEST_STRICT:-}" = 1 ]; then bad "$1 (could not run: needs $2)"
  else echo "  SKIP  $1 (needs $2)"; SKIP=$((SKIP+1)); fi
}
# A FAIL with no output is a guard nobody can act on (CI logs only showed the name):
# keep the command's output and print its tail when it fails.
check() {
  local out
  if out="$(eval "$2" 2>&1)"; then ok "$1"; else
    bad "$1"
    # Head, tail, and every failure marker in between (jest/pytest/TAP/eslint): the names
    # of what failed are usually in the middle of a long run, which head+tail alone drop.
    printf '%s\n' "$out" | awk 'NR<=12 || NR>n-28 {print}' n="$(printf '%s\n' "$out" | wc -l)" | sed 's/^/        | /'
    printf '%s\n' "$out" | grep -E '^\s*(FAIL |ERROR|✕|● |not ok|E   |FAILED |error[: ])' | awk '!seen[$0]++' | head -40 | sed 's/^/        ! /'
  fi
}
# refuses NAME CMD [NEEDLE]: CMD must fail. With NEEDLE, its output must also name the
# rule that fired: without that, a plant that fails for an unrelated reason (an import
# error, a syntax error in the hook, pytest exit 5) reads as "the guard caught it".
refuses() {
  local out
  if out="$(eval "$2" 2>&1)"; then bad "$1 (still green)"; return; fi
  if [ -z "${3:-}" ] || grep -qF -- "$3" <<<"$out"; then ok "$1"; else bad "$1 (failed, but not on: $3)"; fi
}

APP="$T/app"; mkdir -p "$APP"
echo "Renderer"
check "renders" "python3 '$KIT/scripts/render.py' --target '$APP' --name 'Penny Jar' --slug penny-jar --bundle-id com.alex.pennyjar --owner alex --one-liner 'Savers build a daily streak'"
refuses "no leftover placeholders" "grep -rIl '__APP_\\|__BUNDLE_ID__\\|__OWNER__\\|__SCHEME__\\|__ONE_LINER__' '$APP' --exclude-dir=node_modules"
check ".claude/skills symlink" "[ -L '$APP/.claude/skills' ] && [ -f '$APP/.claude/skills/pr-review/SKILL.md' ]"
check ".codex agents + config are valid TOML" "python3 -c \"import tomllib,glob; [tomllib.load(open(f,'rb')) for f in glob.glob('$APP/.codex/**/*.toml', recursive=True)]\""
check "JSON configs parse" "for f in '$APP/.mcp.json' '$APP/.claude/settings.json' '$APP/.codex/hooks.json' '$APP/mobile/eas.json' '$APP/mobile/app.json'; do python3 -m json.tool \"\$f\"; done"
refuses "rejects unsafe names" "python3 '$KIT/scripts/render.py' --target '$T/x' --name 'a\"b' --slug abc --bundle-id com.a.b --owner o"
check "protected files survive --force (and an unusable palette makes render exit 2, not 0)" "echo '{\"name\":\"mine\",\"color\":{}}' > '$APP/design/tokens.json'; python3 '$KIT/scripts/render.py' --target '$APP' --name P --slug penny-jar --bundle-id com.a.b --owner o --force; [ \$? -eq 2 ] && grep -q mine '$APP/design/tokens.json'"
cp "$KIT/template/design/tokens.json" "$APP/design/tokens.json"
python3 "$KIT/scripts/render.py" --target "$APP" --name "Penny Jar" --slug penny-jar --bundle-id com.alex.pennyjar --owner alex --one-liner "Savers build a daily streak" --force >/dev/null

echo "Design"
check "light theme emits a widened mode type (tsc-safe)" "python3 -c \"import json,sys; sys.path.insert(0,'$KIT/scripts'); import render; d=json.load(open('$APP/design/tokens.json')); d['mode']='light'; assert 'mode: \\\"light\\\" | \\\"dark\\\" = \\\"light\\\"' in render.tokens_ts(d)\""
check "default tokens pass contrast" "python3 '$KIT/scripts/check_contrast.py' '$APP/design/tokens.json'"
refuses "contrast check catches a dim ink" "python3 -c \"import json;d=json.load(open('$APP/design/tokens.json'));d['color']['dark']['inkFaint']='#4E525B';json.dump(d,open('$T/bad.json','w'))\" && python3 '$KIT/scripts/check_contrast.py' '$T/bad.json'"

echo "Backend"
check "pytest green" "cd '$APP' && APP_VENV_HOME='$T/venvs' ./scripts/dev-venv.sh python -m pytest -q"
check "ruff clean on the pristine template (rules pinned in pyproject)" "cd '$APP' && ./.venv/bin/ruff check backend tests"
check "/health is ok once Supabase + Sentry are wired (no phantom features)" "cd '$APP' && SUPABASE_URL=x SUPABASE_SECRET_KEY=x SENTRY_DSN=x ./.venv/bin/python -c \"from fastapi.testclient import TestClient; from backend.main import create_app; assert TestClient(create_app()).get('/health').json()['status'] == 'ok'\""
cp "$APP/backend/routers/me.py" "$T/me.bak"
sed -i.bak 's/.eq("id", user.id).limit(1)/.limit(1)/' "$APP/backend/routers/me.py"
refuses "ownership test fails when scoping is removed" "cd '$APP' && ./.venv/bin/python -m pytest -q tests/test_me.py"
cp "$T/me.bak" "$APP/backend/routers/me.py"; rm -f "$APP/backend/routers/me.py.bak"

echo "Guards"
cd "$APP" && git init -q -b main && git config core.hooksPath .githooks && git add -A
G="git -c user.email=t@example.com -c user.name=selftest"
refuses "pre-commit refuses commit on main" "$G commit -qm x"
check "bootstrap commit allowed with flag" "APPBOX_BOOTSTRAP=1 $G commit -qm bootstrap"
git switch -qc feat/selftest
echo "X=1" > .env; git add -f .env
refuses "pre-commit refuses staged .env" "$G commit -qm env"
git restore --staged .env; rm .env
echo 'k = "sk-ant-abcdefghijklmnopqrstuvwxyz0123"' > leak.py; git add leak.py
refuses "pre-commit refuses key-shaped strings" "$G commit -qm leak"
git restore --staged leak.py; rm leak.py
BR="ma""in"
refuses "Claude bash-safety blocks push to $BR" "printf '{\"tool_input\":{\"command\":\"git push origin %s\"}}' $BR | bash .claude/hooks/bash-safety.sh"
check "path rule injected for migrations" "printf '{\"tool_input\":{\"file_path\":\"%s/supabase/migrations/x.sql\"},\"session_id\":\"st%s\"}' '$APP' \$RANDOM | CLAUDE_PROJECT_DIR='$APP' python3 .claude/hooks/inject-path-rules.py | grep -q db-migrations"
CODEX_CMD="$(python3 -c "import json;print(json.load(open('.codex/hooks.json'))['hooks']['SessionStart'][0]['hooks'][0]['command'])")"
check "Codex SessionStart hook runs" 'bash -c "$CODEX_CMD" > "$T/codex-hook.out" && grep -q "Session start" "$T/codex-hook.out"'

# Area checks: each scripts/selftest.d/<area>.sh is sourced here with $KIT, $APP
# (rendered app, a git repo on branch feat/selftest), $T (temp dir), and the
# check/refuses helpers. Add a file per area instead of editing this script.
for extra in "$HERE"/selftest.d/*.sh; do
  [ -f "$extra" ] || continue
  echo "$(basename "$extra" .sh)"
  cd "$APP" && . "$extra"
done

if [ "$MOBILE" = 1 ]; then
  echo "Mobile (real Expo app)"
  M="$T/m"; mkdir -p "$M" && cd "$M"
  if npx --yes create-expo-app@latest mobile --template blank-typescript --no-install </dev/null >/dev/null 2>&1 && rm -rf mobile/.claude && cd mobile \
     && rm -f App.tsx index.ts && npm pkg set main=expo-router/entry \
     && npm install --no-audit --no-fund --loglevel=error >/dev/null 2>&1 \
     && bash "$KIT/scripts/mobile-deps.sh" . >/dev/null 2>&1 \
     && cd .. && python3 "$KIT/scripts/render.py" --target . --name "Penny Jar" --slug penny-jar --bundle-id com.alex.pennyjar --owner alex --one-liner "x" --force >/dev/null; then
    cd "$M/mobile"
    check "npm run gates green" "npm run -s gates"
    printf 'import { Text } from "react-native";\nexport default function X() {\n  return <Text style={{ color: "#ff0000" }}>{process.env.EXPO_PUBLIC_UNWIRED}</Text>;\n}\n' > "app/(app)/planted.tsx"
    refuses "eslint catches hex literal" "npx eslint 'app/(app)/planted.tsx'"
    refuses "analytics guard catches uninstrumented screen" "node scripts/check-analytics-coverage.js"
    refuses "env guard catches unwired EXPO_PUBLIC var" "node scripts/check-eas-shipping-env.js"
    rm "app/(app)/planted.tsx"
    # Area checks that need this real Expo app: an area defines mobile_check_<area>(),
    # run here in name order with cwd = the app's mobile/ (scripts/selftest.d/*.sh).
    for fn in $(declare -F | awk '$3 ~ /^mobile_check_/ {print $3}'); do cd "$M/mobile" && "$fn"; done
  else
    bad "mobile scaffold (create-expo-app / expo install; needs registry access)"
  fi
fi

echo
echo "selftest: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$SKIP" = 0 ] || echo "selftest: skipped checks did NOT run; install what they need, or run in kit CI"
[ "$KEEP" = 1 ] && echo "kept: $T"
exit "$FAIL"
