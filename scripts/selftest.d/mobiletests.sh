# Mobile tests: every UI/lib module has a test or a stated reason, the
# gates run jest with a coverage floor over ALL of app/components/lib, and the
# component behaviour tests ship with the template. The tests themselves run in the
# nightly --mobile job (a real Expo app); the presence lint is fs-only, so it runs here.

MT="$APP/mobile"
check "test presence: every components/ui + lib module has a test or a stated reason" \
  "cd '$MT' && node scripts/check-test-presence.js"
check "gates run the presence lint and jest with coverage; mobile-deps sets the floor over app/components/lib" \
  "grep -q 'check-test-presence.js && jest --ci --coverage' '$KIT/scripts/mobile-deps.sh' && grep -q 'jest.coverageThreshold.global.statements=' '$KIT/scripts/mobile-deps.sh' && grep -q 'collectCoverageFrom\[2\]=lib/' '$KIT/scripts/mobile-deps.sh'"
check "component tests cover haptic grading, announcements and the kit primitives" \
  "f='$MT/components/__tests__/components.test.tsx'; for w in 'ImpactFeedbackStyle.Medium' 'announceForAccessibility' 'ToastProvider' 'SkeletonCard' 'EmptyState' 'Celebration' 'Toggle' 'Media' 'StatCard' 'ErrorNotice' 'Chip' 'ListRow' 'UpdateBanner'; do grep -q \"\$w\" \"\$f\" || exit 1; done"

_tp_plant() {
  local c="$T/tp-plant"; rm -rf "$c"; mkdir -p "$c"
  (cd "$MT" && tar --exclude=node_modules -cf - app components lib scripts __tests__ locales 2>/dev/null) | (cd "$c" && tar -xf -) || return 1
  (cd "$c" && "$1") || return 1
  (cd "$c" && node scripts/check-test-presence.js >/dev/null 2>&1)
}
_tp_new() { printf 'export function Rating() { return null; }\n' > components/ui/Rating.tsx; }
_tp_stale() { sed -i 's|^  "lib/monitoring": .*|&\n  "lib/gone": "a module that was deleted",|' scripts/check-test-presence.js && grep -q 'lib/gone' scripts/check-test-presence.js; }
_tp_barrel() { sed -i 's|import { OfflineBanner } from "../ui";|import { Button as OfflineBanner } from "../ui";|' components/__tests__/offline-banner.test.tsx && grep -q 'Button as OfflineBanner' components/__tests__/offline-banner.test.tsx; }
refuses "test presence: a new primitive with no test fails" "_tp_plant _tp_new"
refuses "test presence: an allowlist entry for a module that doesn't exist fails" "_tp_plant _tp_stale"
refuses "test presence: a module only 'tested' through the barrel by a different name fails" "_tp_plant _tp_barrel"
