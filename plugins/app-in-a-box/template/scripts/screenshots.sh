#!/usr/bin/env bash
# Screenshots of the app's screens, light and dark, for the craft review (pr-review hands
# them to the craft-reviewer agent; build-feature's definition of done says look at them).
# Exports the app for web in demo mode (no accounts, seeded data), then shoots each route
# at 390x844 with scripts/screenshots.mjs (Playwright + Chromium).
#
#   scripts/screenshots.sh [--out DIR] [--changed BASE] [--dist DIR] [--list] [ROUTE...]
#
#   ROUTE...        routes to shoot: / /settings /sign-in
#   --changed BASE  shoot the routes this branch changed since BASE (e.g. origin/main): a
#                   changed file under mobile/app/ is its route; a change under
#                   mobile/components/ or the theme reshoots every route (and /gallery)
#   --out DIR       where the PNGs go (default .appbox/shots, git-ignored)
#   --dist DIR      reuse an existing web export instead of building one
#   --list          print the routes it would shoot, and stop
# Neither routes nor --changed: every route. Prints one PNG path per line.
# Exit 0 shots written (or nothing to shoot), 1 a route didn't render or the export
# failed, 2 bad usage, 3 Playwright/Chromium missing (take the shots another way).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/.appbox/shots" BASE="" DIST="" LIST=0
ROUTES=()
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --changed) BASE="$2"; shift 2 ;;
    --dist) DIST="$2"; shift 2 ;;
    --list) LIST=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*) echo "screenshots: unknown option $1" >&2; exit 2 ;;
    *) ROUTES+=("$1"); shift ;;
  esac
done

# mobile/app/(app)/settings.tsx -> /settings; layouts, + routes and [params] have no URL of
# their own to open.
route_of() {
  local r="${1#mobile/app/}"
  r="${r%.tsx}"; r="${r%.ts}"; r="${r%.web}"
  case "$(basename "$r")" in _*|+*) return 0 ;; esac
  case "$r" in *\[*) echo "screenshots: skipping $1 (a [param] route; pass a real URL)" >&2; return 0 ;; esac
  r="$(printf '%s' "$r" | sed -E 's#\([^/]*\)/##g; s#(^|/)index$##')"
  printf '/%s\n' "$r"
}
all_routes() {
  (cd "$ROOT" && find mobile/app -name '*.tsx' -not -path '*/__tests__/*' | sort | while read -r f; do route_of "$f"; done)
}

if [ -n "$BASE" ]; then
  changed="$(git -C "$ROOT" diff --name-only "$BASE"...HEAD -- mobile/app mobile/components mobile/lib/theme.ts mobile/lib/tokens.ts)"
  if printf '%s\n' "$changed" | grep -qE '^mobile/(components|lib)/'; then
    while read -r r; do ROUTES+=("$r"); done < <(all_routes)
  else
    while read -r f; do [ -n "$f" ] && [ -f "$ROOT/$f" ] && { r="$(route_of "$f")"; [ -n "$r" ] && ROUTES+=("$r"); }; done <<<"$changed"
  fi
  [ ${#ROUTES[@]} -gt 0 ] || { echo "screenshots: no screen changed since $BASE; nothing to shoot" >&2; exit 0; }
elif [ ${#ROUTES[@]} -eq 0 ]; then
  while read -r r; do ROUTES+=("$r"); done < <(all_routes)
fi
# Unique, in order (no mapfile: macOS ships bash 3.2).
UNIQUE=()
for r in "${ROUTES[@]}"; do
  case " ${UNIQUE[*]-} " in *" $r "*) ;; *) [ -n "$r" ] && UNIQUE+=("$r") ;; esac
done
[ "$LIST" = 0 ] || { printf '%s\n' "${UNIQUE[@]}"; exit 0; }

if [ -n "$DIST" ]; then
  DIST="$(cd "$DIST" && pwd)"
else
  [ -d "$ROOT/mobile/node_modules" ] || { echo "screenshots: run npm install in mobile/ first" >&2; exit 1; }
  DIST="$(mktemp -d)/web"
  # --dev keeps __DEV__ on, which demo mode requires (a release bundle ignores it).
  if ! (cd "$ROOT/mobile" && EXPO_PUBLIC_DEMO=1 CI=1 npx expo export --platform web --dev --output-dir "$DIST" >"$DIST.log" 2>&1); then
    echo "screenshots: the web export failed; its log:" >&2; tail -30 "$DIST.log" >&2; exit 1
  fi
fi
mkdir -p "$OUT" && OUT="$(cd "$OUT" && pwd)"
cd "$ROOT/mobile" && exec node "$ROOT/scripts/screenshots.mjs" "$DIST" "$OUT" "${UNIQUE[@]}"
