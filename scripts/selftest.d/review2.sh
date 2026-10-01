# Mobile review #2 (PUL-397): sourced by selftest.sh with $KIT, $APP, $T and the
# check/refuses helpers. Fast static pins on the rendered app (no npm). The
# behaviour itself is proven by jest under --mobile (`npm run gates`):
# lib/__tests__/{auth,query-persist,push,api-401,export,demo,links}.test.* and
# __tests__/{sign-in,delete-account,deep-link-replay}.test.tsx.
R2="$APP/mobile"

check "cache owner is set synchronously in the auth handler, not a post-render effect" \
  "grep -q 'setCacheOwner' '$R2/lib/auth.tsx' && ! grep -q 'useClearCacheOnUserChange' '$R2/lib/auth.tsx'"
check "getSession has a catch (the splash always hides)" \
  "grep -q '\.catch(() => null)' '$R2/lib/auth.tsx'"
check "persisted cache is owner-stamped and checked on restore" \
  "grep -q 'owner: cacheOwner' '$R2/lib/query.ts' && grep -q 'saved.owner !== userId' '$R2/lib/query.ts'"
check "push token is stored with its user; a 401 runs endSession" \
  "grep -q 'JSON.stringify({ token, userId }' '$R2/lib/push.ts' && grep -q 'endSession({ unregisterPush: false })' '$R2/lib/api.ts' && ! grep -q 'status === 401) await signOutThisDevice' '$R2/lib/api.ts'"
check "export deletes its cache file and defers the web revoke" \
  "grep -q 'file.delete()' '$R2/lib/export.ts' && grep -q 'setTimeout(() => revoke(url)' '$R2/lib/export.ts'"
check "demo mode is gated on __DEV__" \
  "grep -q 'export const DEMO = __DEV__ &&' '$R2/lib/demo.ts'"
check "delete-account: sign-out after a successful DELETE has its own fallback" \
  "grep -q 'forceLocalSignOut' '$R2/app/delete-account.tsx'"
check "sign-in: email locked after send, errors through t()" \
  "grep -q 'editable={!sent}' '$R2/app/(auth)/sign-in.tsx' && grep -q 't(\`auth.errors.' '$R2/app/(auth)/sign-in.tsx'"
refuses "/delete-account is not deep-linkable" \
  "grep -q 'LINKABLE_ROUTES.*delete-account' '$R2/lib/links.ts'"
check "signed-out deep links replay after sign-in" \
  "grep -q 'notePendingLink' '$R2/app/+native-intent.tsx' && grep -q 'usePendingLinkReplay' '$R2/app/_layout.tsx'"
