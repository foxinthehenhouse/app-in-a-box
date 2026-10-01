# Dogfood-run fixes (PUL-539): sourced by selftest.sh with $KIT, $APP, $T and check/refuses.
# Each check pins a kit fix found by building a real app on the kit (log: Forge docs/product/discovery/APP_IN_A_BOX_DOGFOOD_LOG.md).

_expo_before_git() {
  local f="$KIT/skills/scaffold/SKILL.md" a b
  a=$(grep -n 'create-expo-app@latest mobile .*</dev/null' "$f" | head -1 | cut -d: -f1)
  b=$(grep -n '^git init -b main' "$f" | head -1 | cut -d: -f1)
  [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ] && grep -qx 'rm -rf mobile/\.claude' "$f"
}
check "scaffold creates the Expo app before git init, stdin closed, nested .claude removed" "_expo_before_git"

refuses "framework tests don't wait on the template Home's copy (replacing Home can't break them)" \
  "grep -qE 'Hi, Sam|home\\.greeting' '$APP/mobile/__tests__/demo-flow.test.tsx' '$APP/mobile/__tests__/i18n-pseudo.test.tsx'"

check "pseudo-locale test treats every demo-seed string as user data (lazy-loaded after the env var)" \
  "grep -q 'leaves(DEMO_SEED)' '$APP/mobile/__tests__/i18n-pseudo.test.tsx' \
   && grep -q 'require(\"../lib/demo\")' '$APP/mobile/__tests__/i18n-pseudo.test.tsx' \
   && ! grep -q '^import .*from \"../lib/demo\"' '$APP/mobile/__tests__/i18n-pseudo.test.tsx'"

check "Home keeps the testIDs the framework tests wait on" \
  "grep -q 'testID=\"home-screen\"' '$APP/mobile/app/(app)/index.tsx' && grep -q 'testID=\"home-skeleton\"' '$APP/mobile/app/(app)/index.tsx'"
