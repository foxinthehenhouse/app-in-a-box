# v1.0 production, mobile side (PUL-397): sourced by selftest.sh with $KIT, $APP (the
# rendered app, a git repo), $T and the check/refuses helpers. Fast: python + node,
# no npm. The full mobile proof (jest for delete-account, offline rollback, push,
# forms, i18n pseudo-locale, deep links, request ids, export) runs under --mobile via
# `npm run gates`. Every plant is reverted and the check at the end proves it.

V1_PY="$APP/.venv/bin/python"
V1_STR="node '$APP/mobile/scripts/check-hardcoded-strings.js'"

# ---- data export endpoint ------------------------------------------------------------
check "export endpoint tests green (scoped, rate-limited, wire-paired)" \
  "cd '$APP' && '$V1_PY' -m pytest -q -p no:warnings tests/test_v1_export.py tests/test_wire_contract.py tests/test_scoping_static.py"

# name, file (relative to $APP), sed expression, test file(s)
_v1_negative() {
  cp "$APP/$2" "$T/v1-neg.bak"
  sed -i.sedbak "$3" "$APP/$2" && rm -f "$APP/$2.sedbak"
  if cmp -s "$T/v1-neg.bak" "$APP/$2"; then
    bad "$1 (planted change did not apply; update v1mobile.sh)"
  else
    refuses "$1" "cd '$APP' && '$V1_PY' -m pytest -q -x -p no:warnings $4"
  fi
  cp "$T/v1-neg.bak" "$APP/$2"
}

_v1_negative "export test fails when a reader drops its user filter (another user's rows leak)" \
  backend/routers/export.py '/"push_tokens"/,/execute/ s/\.eq("user_id", user_id)//' tests/test_v1_export.py
_v1_negative "export test fails when the profile read is unscoped" \
  backend/routers/export.py 's/\.eq("id", user_id)//' tests/test_v1_export.py
_v1_negative "export test fails when the rate limit is removed" \
  backend/routers/export.py 's/dependencies=\[Depends(rate_limit("me.export", 5, 3600))\]/dependencies=[]/' tests/test_v1_export.py
_v1_negative "wire contract fails when DataExportWire drifts from the model" \
  mobile/lib/api.ts 's/^  exportedAt: string;/  exported: string;/' tests/test_wire_contract.py

cp "$APP/supabase/migrations/20260930120000_rls_policies_initplan.sql" "$T/v1-mig.bak"
printf '\ncreate table if not exists public.notes (\n  id bigint primary key,\n  user_id uuid not null references auth.users (id) on delete cascade\n);\n' \
  >> "$APP/supabase/migrations/20260930120000_rls_policies_initplan.sql"
refuses "export test fails when a new user-owned table isn't exported" \
  "cd '$APP' && '$V1_PY' -m pytest -q -x -p no:warnings tests/test_v1_export.py -k every_user_owned_table"
cp "$T/v1-mig.bak" "$APP/supabase/migrations/20260930120000_rls_policies_initplan.sql"

# ---- hardcoded strings (i18n) ----------------------------------------------------------
check "hardcoded-string check passes on the pristine template (app/ + components/)" "$V1_STR"
check "gates run the hardcoded-string check + the shared jest setup" \
  "grep -q 'node scripts/check-hardcoded-strings.js' '$KIT/scripts/mobile-deps.sh' && grep -q 'jest.setupFiles' '$KIT/scripts/mobile-deps.sh' && [ -f '$APP/mobile/jest.setup.ts' ]"

PLANT="$APP/mobile/app/(app)/planted-strings.tsx"
printf 'import { Text } from "react-native";\nexport default function P() {\n  return <Text>Save your changes</Text>;\n}\n' > "$PLANT"
refuses "hardcoded-string check catches a planted JSX literal" "$V1_STR"
printf 'import { Button } from "../../components/ui";\nexport default function P() {\n  return <Button label="Save changes" onPress={() => undefined} />;\n}\n' > "$PLANT"
refuses "hardcoded-string check catches a literal user-facing prop" "$V1_STR"
printf 'export function f(toast: { success: (m: string) => void }) {\n  toast.success("Saved!");\n}\n' > "$PLANT"
refuses "hardcoded-string check catches a literal toast" "$V1_STR"
printf 'import { Text } from "react-native";\nexport default function P() {\n  return <Text>Penny Jar</Text>; // i18n-ignore: brand name\n}\n' > "$PLANT"
check "an explained i18n-ignore passes" "$V1_STR"
printf 'type Props<T> = { v: T };\nexport function g<T extends object>(\n  p: Props<T>,\n): Omit<Props<T>, "v"> {\n  return p;\n}\n' > "$PLANT"
check "TS generics aren't mistaken for JSX text" "$V1_STR"
rm -f "$PLANT"
CPLANT="$APP/mobile/components/ui/Planted.tsx"
printf 'import { Text } from "react-native";\nexport function Planted() {\n  return <Text>Loading…</Text>;\n}\n' > "$CPLANT"
refuses "hardcoded-string check covers the component library too" "$V1_STR"
rm -f "$CPLANT"

check "i18n: English strings + the pseudo-locale screen test ship with the template" \
  "grep -q 'export const en = {' '$APP/mobile/locales/en.ts' && grep -q 'PSEUDO_LOCALE' '$APP/mobile/lib/i18n.ts' && [ -f '$APP/mobile/__tests__/i18n-pseudo.test.tsx' ]"

# ---- OTA, deep links, push, offline wiring ---------------------------------------------
check "OTA: fingerprint runtime policy + a channel on every eas.json build profile" \
  "python3 -c \"import json;e=json.load(open('$APP/mobile/app.json'))['expo'];assert e['runtimeVersion']=={'policy':'fingerprint'} and e['updates']['fallbackToCacheTimeout']==0;b=json.load(open('$APP/mobile/eas.json'))['build'];assert all(b[p].get('channel')==p for p in ('development','preview','production'))\""
check "deep links: +native-intent maps through the one resolver" \
  "grep -q 'resolveDeepLink' '$APP/mobile/app/+native-intent.tsx' && grep -q 'LINKABLE_ROUTES' '$APP/mobile/lib/links.ts' && ! grep -q '__SCHEME__' '$APP/mobile/lib/links.ts'"
cp "$APP/mobile/app.json" "$T/v1-app.bak"
check "set-app-domain.js writes associated domains + an autoVerify intent filter" \
  "node '$APP/mobile/scripts/set-app-domain.js' links.example.com --team-id ABCDE12345 --sha256 AA:BB >/dev/null && python3 -c \"import json;e=json.load(open('$APP/mobile/app.json'))['expo'];assert e['extra']['appDomain']=='links.example.com' and e['ios']['associatedDomains']==['applinks:links.example.com'] and e['android']['intentFilters'][0]['autoVerify']\""
refuses "set-app-domain.js rejects a malformed domain" "node '$APP/mobile/scripts/set-app-domain.js' 'not a domain'"
cp "$T/v1-app.bak" "$APP/mobile/app.json"
check "offline mutations pause (networkMode online), queries read offline-first" \
  "grep -q 'mutations: { networkMode: \"online\"' '$APP/mobile/lib/query.ts' && grep -q 'networkMode: \"offlineFirst\"' '$APP/mobile/lib/query.ts'"
check "demo mode answers every endpoint the app calls" \
  "( for r in 'GET /api/v1/me' 'PATCH /api/v1/me' 'DELETE /api/v1/me' 'POST /api/v1/me/push-token' 'DELETE /api/v1/me/push-token' 'GET /api/v1/me/export'; do grep -qF \"\\\"\$r\\\"\" '$APP/mobile/lib/demo.ts' || exit 1; done )"

check "every v1 plant was reverted" \
  "cd '$APP' && git diff --quiet -- mobile backend supabase tests && [ -z \"\$(git status --porcelain --untracked-files=all -- mobile backend supabase tests)\" ]"
