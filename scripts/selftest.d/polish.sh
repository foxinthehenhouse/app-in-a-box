# v0.2 polish checks (sourced by scripts/selftest.sh with $KIT, $APP, $T and the
# check/refuses helpers). Fast: python + node only, no npm installs.
P="python3 -c"
TOK="$KIT/template/design/tokens.json"
EXT="$KIT/../../examples/lonely-socks/tokens.json"

check "default + example tokens ship light AND dark palettes" \
  "for f in '$TOK' '$EXT'; do $P \"import json;d=json.load(open('\$f'));c=d['color'];assert isinstance(c['light'],dict) and isinstance(c['dark'],dict) and set(c['light'])==set(c['dark'])\"; done"
check "tokens carry motion, type roles, elevation, opacity" \
  "$P \"import json;d=json.load(open('$TOK'));assert d['motion']['duration'] and d['motion']['spring'] and len(d['type'])==7 and d['elevation'] and d['opacity']\""
check "contrast passes in both modes (default + Lonely Socks)" \
  "python3 '$KIT/scripts/check_contrast.py' '$TOK' && python3 '$KIT/scripts/check_contrast.py' '$EXT'"
refuses "contrast catches a dim DARK-mode ink" \
  "$P \"import json;d=json.load(open('$TOK'));d['color']['dark']['inkFaint']='#4E525B';json.dump(d,open('$T/bad-dark.json','w'))\" && python3 '$KIT/scripts/check_contrast.py' '$T/bad-dark.json'"
refuses "contrast catches a pale LIGHT-mode ink" \
  "$P \"import json;d=json.load(open('$TOK'));d['color']['light']['inkDim']='#B8B4AA';json.dump(d,open('$T/bad-light.json','w'))\" && python3 '$KIT/scripts/check_contrast.py' '$T/bad-light.json'"
refuses "schema rejects a palette missing a key in one mode" \
  "$P \"import json;d=json.load(open('$TOK'));del d['color']['light']['danger'];json.dump(d,open('$T/bad-keys.json','w'))\" && python3 '$KIT/scripts/check_contrast.py' '$T/bad-keys.json'"
check "v1 single-palette tokens still validate (backward compatible)" \
  "$P \"import json;d=json.load(open('$TOK'));d['color']=d['color']['dark'];d['mode']='dark';[d.pop(k) for k in ('type','motion')];json.dump(d,open('$T/v1.json','w'))\" && python3 '$KIT/scripts/check_contrast.py' '$T/v1.json'"

check "rendered tokens.ts has both palettes, schemes, motion + type roles" \
  "grep -q 'export const palettes' '$APP/mobile/lib/tokens.ts' && grep -q '\"light\": {' '$APP/mobile/lib/tokens.ts' && grep -q '\"dark\": {' '$APP/mobile/lib/tokens.ts' && grep -q 'schemes: readonly ColorScheme\[\] = \[\"light\", \"dark\"\]' '$APP/mobile/lib/tokens.ts' && grep -q 'export const motion' '$APP/mobile/lib/tokens.ts' && grep -q 'export const typeRoles' '$APP/mobile/lib/tokens.ts'"
check "v1 tokens render locked to their mode (tokens.ts + app.json)" \
  "$P \"import json,sys;sys.path.insert(0,'$KIT/scripts');import render;d=json.load(open('$T/v1.json'));ts=render.tokens_ts(d);assert 'schemes: readonly ColorScheme[] = [\\\"dark\\\"]' in ts and 'typeRoles' in ts;a=render.theme_app_json({'expo':{}},d);assert a['expo']['userInterfaceStyle']=='dark'\""
check "app.json: automatic appearance + splash background per mode" \
  "$P \"import json;e=json.load(open('$APP/mobile/app.json'))['expo'];assert e['userInterfaceStyle']=='automatic';s=[p for p in e['plugins'] if isinstance(p,list) and p[0]=='expo-splash-screen'][0][1];assert s['backgroundColor']!=s['dark']['backgroundColor']\""
check "brand icons generated as valid PNGs" \
  "for f in icon adaptive-icon splash-icon favicon; do head -c 8 '$APP/mobile/assets/brand/'\$f.png | od -An -tx1 | grep -q '89 50 4e 47'; done"

check "no hex literals in template screens/components/lib (tokens only)" \
  "! grep -rnE \"['\\\"]#[0-9a-fA-F]{3,8}['\\\"]\" '$APP/mobile/app' '$APP/mobile/components' '$APP/mobile/lib' --include=*.ts --include=*.tsx | grep -v 'lib/tokens.ts'"
check "no deprecated RN SafeAreaView in the template" \
  "! grep -rn 'SafeAreaView,\\|SafeAreaView }' '$APP/mobile' --include=*.tsx | grep 'from \"react-native\"'"
check "tabs are native tabs with SF + Material icons" \
  "grep -q 'unstable-native-tabs' '$APP/mobile/app/(app)/_layout.tsx' && grep -q 'sf=' '$APP/mobile/app/(app)/_layout.tsx' && grep -q 'md=' '$APP/mobile/app/(app)/_layout.tsx'"
check "a formSheet route is registered once, on the root Stack" \
  "grep -q 'presentation: \"formSheet\"' '$APP/mobile/app/_layout.tsx' && ! grep -rq formSheet '$APP/mobile/app/(app)'"

check "env guard allowlists EXPO_PUBLIC_DEMO and passes" \
  "grep -q EXPO_PUBLIC_DEMO '$APP/mobile/scripts/check-eas-shipping-env.js' && node '$APP/mobile/scripts/check-eas-shipping-env.js'"
refuses "env guard refuses demo mode in a shipping eas.json profile" \
  "rm -rf '$T/envg' && mkdir -p '$T/envg' && cp -R '$APP/mobile/scripts' '$APP/mobile/lib' '$APP/mobile/app' '$APP/mobile/components' '$T/envg/' && $P \"import json;d=json.load(open('$APP/mobile/eas.json'));d['build']['production']['env']['EXPO_PUBLIC_DEMO']='1';json.dump(d,open('$T/envg/eas.json','w'))\" && node '$T/envg/scripts/check-eas-shipping-env.js'"
check "analytics guard passes on the template (gallery + sheet instrumented)" \
  "node '$APP/mobile/scripts/check-analytics-coverage.js'"

check "demo.sh renders Lonely Socks (--no-install) with demo mode on" \
  "'$KIT/scripts/demo.sh' '$T/demo' --no-install && grep -q 'Lonely Socks' '$T/demo/mobile/lib/app.ts' && grep -q '\"name\": \"playful\"' '$T/demo/design/tokens.json' && grep -q '^EXPO_PUBLIC_DEMO=1' '$T/demo/mobile/.env'"
