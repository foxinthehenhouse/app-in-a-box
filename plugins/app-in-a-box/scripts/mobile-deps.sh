#!/usr/bin/env bash
# Install the template's mobile dependencies into an Expo app created with
# `create-expo-app --template blank-typescript`, and set the npm scripts.
# ONE list, used by the scaffold skill, scripts/demo.sh and the kit selftest, so
# they can't drift. Versions come from the Expo SDK (`npx expo install`), never
# from this file.
#
#   mobile-deps.sh <path/to/mobile>
#
# Falls back to EXPO_OFFLINE=1 (the SDK's bundled version map) when Expo's API is
# unreachable (corporate proxies); npm itself still needs the registry.
set -euo pipefail
cd "${1:?usage: mobile-deps.sh <mobile dir>}"

# react-dom + react-native-web: web target (and demo mode in a browser). react-dom
# MUST be in this first install: added later, npm picks a newer React than the SDK
# pins and every later install fails with ERESOLVE.
RUNTIME=(
  react-dom react-native-web
  expo-router react-native-screens react-native-safe-area-context expo-linking expo-constants
  expo-status-bar expo-system-ui expo-splash-screen expo-font
  react-native-reanimated react-native-worklets react-native-gesture-handler
  expo-haptics expo-symbols @shopify/flash-list
  @supabase/supabase-js @react-native-async-storage/async-storage react-native-url-polyfill
  posthog-react-native expo-file-system expo-application expo-device expo-localization
  @sentry/react-native
  # v1.0 production capabilities (built in, not recipes):
  @tanstack/react-query @tanstack/react-query-persist-client @tanstack/query-async-storage-persister
  @react-native-community/netinfo
  expo-notifications expo-updates expo-crypto expo-clipboard expo-sharing
  react-hook-form zod @hookform/resolvers
  i18next react-i18next
)
DEV=(eslint eslint-config-expo jest jest-expo @types/jest @testing-library/react-native)

expo_install() {
  npx expo install "$@" || EXPO_OFFLINE=1 npx expo install "$@"
}

expo_install "${RUNTIME[@]}"
expo_install -- --save-dev "${DEV[@]}"

# jest.resolver: Reanimated 4 / worklets load their JS fallbacks (not the native
# module) under jest; without it any test importing a component crashes.
npm pkg set main=expo-router/entry \
  scripts.lint="eslint ." scripts.typecheck="tsc --noEmit" scripts.test="jest" \
  scripts.web="expo start --web" scripts.demo="EXPO_PUBLIC_DEMO=1 expo start" \
  jest.preset=jest-expo jest.resolver=react-native-worklets/jest/resolver.js \
  "jest.setupFiles[0]=./jest.setup.ts" \
  scripts.check-strings="node scripts/check-hardcoded-strings.js" \
  scripts.gates="tsc --noEmit && eslint . && node scripts/check-analytics-coverage.js && node scripts/check-eas-shipping-env.js && node scripts/check-replay-unmask.js && node scripts/check-hardcoded-strings.js && jest --ci --passWithNoTests"
