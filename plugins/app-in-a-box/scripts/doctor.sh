#!/usr/bin/env bash
# App in a Box doctor. Reports which tools and logins are present.
#
#   doctor.sh preflight   # local tools only (phase 0)
#   doctor.sh accounts    # CLI logins (phase 3)
#   doctor.sh full        # everything + repo gates (phase 7), run from the app root
#
# Prints one line per check: OK / MISSING / WARN, then a summary. Exit code =
# number of required checks that failed (0 = green). Never prints secret values.
set -u
MODE="${1:-preflight}"
FAIL=0

ok()   { printf '  \033[32mOK\033[0m       %-22s %s\n' "$1" "${2:-}"; }
miss() { printf '  \033[31mMISSING\033[0m  %-22s %s\n' "$1" "${2:-}"; FAIL=$((FAIL+1)); }
warn() { printf '  \033[33mWARN\033[0m     %-22s %s\n' "$1" "${2:-}"; }

have() { command -v "$1" >/dev/null 2>&1; }

check_tool() { # name, install hint, required(1/0)
  if have "$1"; then ok "$1" "$("$1" --version 2>/dev/null | head -1)"
  elif [ "${3:-1}" = 1 ]; then miss "$1" "install: $2"
  else warn "$1" "optional, install: $2"; fi
}

preflight() {
  echo "Local tools"
  check_tool git  "https://git-scm.com"
  if have node; then
    major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
    if [ "$major" -ge 20 ]; then ok node "v$(node -v | tr -d v)"; else miss node "need >= 20 (have $(node -v)); https://nodejs.org or nvm install 20"; fi
  else miss node "https://nodejs.org (>= 20)"; fi
  check_tool npm "ships with node"
  py=""
  for c in python3.12 python3.13 python3; do
    if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then py="$c"; break; fi
  done
  if [ -n "$py" ]; then ok python "$($py --version)"; elif have uv; then warn python "no 3.12 on PATH; uv will fetch one (uv python install 3.12)"; else miss python "need 3.12+: brew install python@3.12, or install uv (https://docs.astral.sh/uv)"; fi
  check_tool uv "curl -LsSf https://astral.sh/uv/install.sh -o uv.sh && sh uv.sh (inspect first)" 0
  # Service CLIs aren't needed until phase 3 (accounts); warn now, require then.
  check_tool gh "brew install gh | https://cli.github.com (needed from phase 3)" 0
  check_tool supabase "brew install supabase/tap/supabase, or use npx supabase (needed from phase 3)" 0
  check_tool eas "npm i -g eas-cli (needed from phase 3)" 0
  check_tool railway "brew install railway | npm i -g @railway/cli" 0
  check_tool maestro "https://maestro.mobile.dev (optional: E2E flows)" 0
  if [ "$(uname)" = Darwin ]; then
    if have xcrun && xcrun simctl help >/dev/null 2>&1; then ok xcode "simulator available"; else warn xcode "no iOS simulator; install Xcode for local iOS builds (Expo Go works without it)"; fi
  fi
}

accounts() {
  echo "Service CLIs"
  check_tool gh "brew install gh | https://cli.github.com"
  check_tool supabase "brew install supabase/tap/supabase, or use npx supabase"
  check_tool eas "npm i -g eas-cli"
  echo "Logins"
  if have gh && gh auth status >/dev/null 2>&1; then ok github "$(gh api user -q .login 2>/dev/null)"; else miss github "run: gh auth login"; fi
  if have supabase && supabase projects list >/dev/null 2>&1; then ok supabase "logged in"; else miss supabase "run: supabase login"; fi
  if have eas && eas whoami >/dev/null 2>&1; then ok expo "$(eas whoami 2>/dev/null | head -1)"; else miss expo "run: eas login"; fi
  if have railway; then
    if railway whoami >/dev/null 2>&1; then ok railway "$(railway whoami 2>/dev/null | head -1)"; else miss railway "run: railway login"; fi
  fi
  # Opt-in services: only checked when appbox.yaml's stack chose them (no file yet = check).
  if stack_wants analytics posthog; then
    [ -n "${POSTHOG_PERSONAL_API_KEY:-}" ] && ok posthog "personal key in env" || warn posthog "no POSTHOG_PERSONAL_API_KEY in env (MCP OAuth also works)"
  else ok posthog "not in the stack (analytics declined; the app's calls stay no-ops)"; fi
  if stack_wants errors sentry; then
    [ -n "${SENTRY_AUTH_TOKEN:-}" ] && ok sentry "auth token in env" || warn sentry "no SENTRY_AUTH_TOKEN in env (MCP OAuth also works)"
  else ok sentry "not in the stack (error monitoring declined; monitoring stays a no-op)"; fi
  if stack_wants tracker linear; then
    warn linear "authorise the Linear MCP: /mcp in Claude Code, or codex mcp login linear (restart after)"
  fi
}

# stack_wants <key> <value>: true when appbox.yaml has no stack yet, or stack.<key> is <value>.
stack_wants() {
  [ -f appbox.yaml ] || return 0
  local v
  # Same reading as render.py's read_stack: skip comment lines, strip quotes.
  v=$(awk -v k="$1" '/^[[:space:]]*#/{next} /^stack:/{s=1;next} /^[^ ]/{s=0} s && $1==k":"{gsub(/["\047]/,"",$2); print $2; exit}' appbox.yaml)
  [ -z "$v" ] || [ "$v" = "$2" ]
}

full() {
  preflight; accounts
  echo "Repo"
  [ -f appbox.yaml ] && ok appbox.yaml || miss appbox.yaml "run /app-in-a-box:new-app"
  [ -f .env ] && ok .env "present (gitignored?)" || miss .env "the provision phase (5) writes it"
  if [ -f .env ] && ! git check-ignore -q .env 2>/dev/null; then miss .env-ignored ".env is NOT gitignored"; fi
  [ -f .claude/settings.json ] && ok harness "installed" || miss harness "run the scaffold + harness phases"
  if [ -d mobile ]; then
    (cd mobile && npm run -s gates >/dev/null 2>&1) && ok mobile-gates "tsc + eslint + checks + jest" || miss mobile-gates "cd mobile && npm run gates"
  fi
  if [ -d backend ]; then
    (./scripts/dev-venv.sh python -m pytest -q >/dev/null 2>&1) && ok backend-tests "pytest green" || miss backend-tests "scripts/dev-venv.sh python -m pytest -q"
  fi
  if [ -n "${API_URL:-}" ]; then
    body=$(curl -fsS "$API_URL/health" 2>/dev/null) && ok health "$body" || miss health "$API_URL/health not reachable"
  fi
}

case "$MODE" in
  preflight) preflight ;;
  accounts)  accounts ;;
  full)      full ;;
  *) echo "usage: doctor.sh preflight|accounts|full"; exit 2 ;;
esac
echo
if [ "$FAIL" -eq 0 ]; then echo "Doctor: green"; else echo "Doctor: $FAIL required check(s) failing"; fi
exit "$FAIL"
