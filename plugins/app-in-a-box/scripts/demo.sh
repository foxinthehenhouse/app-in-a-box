#!/usr/bin/env bash
# 60-second demo: render the Lonely Socks example app into <target> and run it
# with NO accounts (EXPO_PUBLIC_DEMO=1: in-memory fake backend + auth, seeded data).
#
#   demo.sh <target> [--no-install]
#
# Default: creates the Expo app, installs deps (scripts/mobile-deps.sh, ~2-3 min),
# overlays the template skinned with the example's tokens, and prints how to run it.
# --no-install: render the files only (fast; used by the kit selftest).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT="$(cd "$HERE/.." && pwd)"
EX="$(cd "$KIT/../../examples/lonely-socks" && pwd)"
TARGET="${1:?usage: demo.sh <target> [--no-install]}"
INSTALL=1
[ "${2:-}" = "--no-install" ] && INSTALL=0
mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"

if [ "$INSTALL" = 1 ] && [ ! -f "$TARGET/mobile/package.json" ]; then
  echo "Creating the Expo app (versions come from the current Expo SDK)..."
  (cd "$TARGET" && npx --yes create-expo-app@latest mobile --template blank-typescript --no-install >/dev/null)
  rm -f "$TARGET/mobile/App.tsx" "$TARGET/mobile/index.ts"
  (cd "$TARGET/mobile" && npm install --no-audit --no-fund --loglevel=error)
  echo "Installing dependencies..."
  "$HERE/mobile-deps.sh" "$TARGET/mobile"
fi

# The example's own decisions (protected from --force, like a real run's).
mkdir -p "$TARGET/design" "$TARGET/docs/product"
cp "$EX/tokens.json" "$TARGET/design/tokens.json"
cp "$EX/appbox.yaml" "$TARGET/appbox.yaml"
cp "$EX/BRIEF.md" "$TARGET/docs/product/BRIEF.md"

field() { sed -n "s/^  $1: *\"\{0,1\}\([^\"]*\)\"\{0,1\} *$/\1/p" "$EX/appbox.yaml" | head -1; }
python3 "$HERE/render.py" --target "$TARGET" --force \
  --name "$(field name)" --slug "$(field slug)" --bundle-id "$(field bundle_id)" \
  --owner "$(field owner_handle)" --one-liner "$(field one_liner)" >/dev/null
python3 "$HERE/check_contrast.py" "$TARGET/design/tokens.json"

# Dev-only switch (gitignored .env): never goes to eas.json, the env guard refuses it there.
ENVF="$TARGET/mobile/.env"
grep -qs '^EXPO_PUBLIC_DEMO=' "$ENVF" || echo "EXPO_PUBLIC_DEMO=1" >> "$ENVF"

cat <<EOF

Lonely Socks is ready at $TARGET (demo mode: no accounts, fake backend, seeded data).

  cd "$TARGET/mobile"
  npx expo start --web        # in a browser
  npx expo start              # scan the QR with Expo Go (iOS / Android)

Sign in with any email and any 6-digit code. Then: Settings -> Appearance to flip
light/dark, Display name opens a native sheet, and Settings -> Component gallery
shows every component in both modes.
EOF
[ "$INSTALL" = 1 ] || echo "(rendered with --no-install: run $HERE/mobile-deps.sh on an Expo app first to run it)"
