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
  expo-status-bar expo-system-ui expo-splash-screen expo-font expo-asset
  react-native-reanimated react-native-worklets react-native-gesture-handler
  expo-haptics expo-symbols @shopify/flash-list
  # expo-dev-client: eas.json's development profile sets developmentClient: true, and
  # `eas build --profile development` exits non-zero (non-interactively) without it.
  expo-dev-client
  # expo-secure-store: the Supabase session lives in the keychain / keystore
  # (lib/secure-store.ts chunks it under SecureStore's 2048-byte value limit).
  expo-secure-store
  # Native UI: @expo/ui gives the platform's own segmented control (SwiftUI / Compose,
  # Liquid Glass on iOS 26); expo-image gives cached, placeholder-first images.
  @expo/ui expo-image
  # expo-glass-effect: Liquid Glass chrome (tab bar, sheet header) when the frozen theme
  # chose glass surfaces; lib/atmosphere.ts falls back to solid below iOS 26.
  expo-glass-effect
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
# babel-plugin-react-compiler: app.json sets experiments.reactCompiler; babel-preset-expo
# loads the plugin from the project, so it must be installed (expo install pins its version).
# knip: dead code (unused files, exports, dependencies) in `npm run gates`; config in
# mobile/knip.jsonc. Pinned to a major because a new major changes what it reports.
DEV=(eslint eslint-config-expo jest jest-expo @types/jest "@testing-library/react-native@^14" babel-plugin-react-compiler "knip@^6")

expo_install() {
  npx expo install "$@" || EXPO_OFFLINE=1 npx expo install "$@"
}

expo_install "${RUNTIME[@]}"
# react-test-renderer is pinned to the INSTALLED React. @testing-library/react-native
# declares an open peer range (>=18.2.0), so npm resolves the newest release, which can
# require a React the SDK does not ship yet (19.3.0 vs SDK 57's 19.2.x) and the whole
# dev install fails with ERESOLVE. Pinning it first keeps the dev install deterministic.
REACT_VERSION="$(node -p "require('./node_modules/react/package.json').version")"
expo_install -- --save-dev "react-test-renderer@${REACT_VERSION}" "${DEV[@]}"

# jest.resolver: Reanimated 4 / worklets load their JS fallbacks (not the native
# module) under jest; without it any test importing a component crashes.
# jest.testTimeout: a route test's first render transforms the whole app, which
# takes ~10-20s on a cold cache (every fresh CI runner). Jest's 5s default failed
# sign-in.test.tsx on exactly that, so allow 30s; a real hang still fails.
npm pkg set main=expo-router/entry \
  scripts.lint="eslint ." scripts.typecheck="tsc --noEmit" scripts.test="jest" \
  scripts.web="expo start --web" scripts.demo="EXPO_PUBLIC_DEMO=1 expo start" \
  jest.preset=jest-expo jest.resolver=react-native-worklets/jest/resolver.js \
  "jest.setupFiles[0]=./jest.setup.ts" \
  scripts.check-strings="node scripts/check-hardcoded-strings.js" \
  scripts.check-contrast="python3 ../scripts/check_contrast.py ../design/tokens.json" \
  scripts.test:guards="node --test scripts/__tests__/*.test.js" \
  scripts.gates="tsc --noEmit && eslint . && knip && node scripts/check-analytics-coverage.js && node scripts/check-eas-shipping-env.js && node scripts/check-maestro-coverage.js && node scripts/check-replay-unmask.js && node scripts/check-hardcoded-strings.js && node scripts/check-design-tells.js && node --test scripts/__tests__/*.test.js && python3 ../scripts/check_contrast.py ../design/tokens.json && python3 ../scripts/check_design.py ../design/tokens.json && node scripts/check-test-presence.js && jest --ci --coverage --coverageReporters=text-summary --passWithNoTests"
npm pkg set jest.testTimeout=30000 --json  # a number, not the string "30000"
# The guard self-tests under scripts/__tests__ run on node:test (no node_modules needed);
# keep jest out of them, or it tries to run them under jest-expo and fails. The same
# goes for the shared test helpers under __tests__/support/.
npm pkg set "jest.testPathIgnorePatterns[0]=/node_modules/" "jest.testPathIgnorePatterns[1]=<rootDir>/scripts/" "jest.testPathIgnorePatterns[2]=/__tests__/support/"
# Coverage floor (part of the gates): measured over ALL of app/, components/ and lib/,
# not just the files some test happens to load, so an untested new screen pulls the
# number down. Set ~2 points under the template's measured coverage (75.9 / 68.8 /
# 70.5 / 77.9): a ratchet, not a target. Raise it as tests land; never lower it to
# get a push through.
npm pkg set "jest.collectCoverageFrom[0]=app/**/*.{ts,tsx}" "jest.collectCoverageFrom[1]=components/**/*.{ts,tsx}" \
  "jest.collectCoverageFrom[2]=lib/**/*.{ts,tsx}" "jest.collectCoverageFrom[3]=!**/__tests__/**" \
  "jest.collectCoverageFrom[4]=!**/*.web.{ts,tsx}"
npm pkg set jest.coverageThreshold.global.statements=74 jest.coverageThreshold.global.branches=66 \
  jest.coverageThreshold.global.functions=68 jest.coverageThreshold.global.lines=76 --json
