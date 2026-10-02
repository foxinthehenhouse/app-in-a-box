# Release path: EAS workflow rules fail on the real bugs they exist for, and
# scripts/rollback-ota.sh picks the right update group (driven by a fake `eas`).
echo "Release path"

PY="$APP/.venv/bin/python"

# Plant a violation in a copy of the app; the workflow test must fail on it.
_eas_plant() {
  local c="$T/eas-plant"; rm -rf "$c"; mkdir -p "$c"
  cp -R "$APP/tests" "$APP/mobile" "$c/" 2>/dev/null || return 1
  rm -rf "$c/mobile/node_modules"
  (cd "$c" && "$1") || return 1
  (cd "$c" && "$PY" -m pytest -q -p no:cacheprovider tests/test_eas_workflows.py >/dev/null 2>&1)
}
WF=mobile/.eas/workflows
_p_env() { sed -i '/^  update_android:/,$s/environment: preview/environment: production/' $WF/pr-preview.yml && grep -q 'environment: production' $WF/pr-preview.yml; }
_p_cross() { sed -i '/^  update_android:/,/^  update_ios:/s/needs: \[get_android_build\]/needs: [get_android_build, get_ios_build]/' $WF/release.yml && grep -q 'get_android_build, get_ios_build' $WF/release.yml; }
_p_param() { sed -i '0,/      profile: preview/s//      profile: preview\n      build_profile: preview/' $WF/pr-preview.yml && grep -q 'build_profile' $WF/pr-preview.yml; }
_p_asc() { python3 -c "import json;p='mobile/eas.json';d=json.load(open(p));d['submit']['production']={'ios':{'ascAppId':'com.example.app'}};json.dump(d,open(p,'w'))"; }
refuses "EAS: a preview OTA published in the production environment fails" "_eas_plant _p_env"
refuses "EAS: an OTA that waits on the other platform's build lookup fails" "_eas_plant _p_cross"
refuses "EAS: an undocumented job param fails" "_eas_plant _p_param"
refuses "EAS: an ascAppId that isn't an Apple ID fails" "_eas_plant _p_asc"

# --- rollback-ota.sh against a fake eas ---------------------------------------------
_fake_eas() {
  local dir="$T/fake-eas"; mkdir -p "$dir"
  cat > "$dir/eas" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "$FAKE_EAS_LOG"
case "$1" in
  update:list) cat "$FAKE_EAS_LIST" ;;
  update:rollback) echo "rolled back" ;;
  *) exit 3 ;;
esac
SH
  chmod +x "$dir/eas"; echo "$dir/eas"
}
_rb() {  # _rb <list-json> <args...>  -> stdout in $T/rb.out, calls in $T/rb.log, rc
  printf '%s' "$1" > "$T/rb.list"; shift; : > "$T/rb.log"
  EAS="$(_fake_eas)" FAKE_EAS_LIST="$T/rb.list" FAKE_EAS_LOG="$T/rb.log" \
    bash "$APP/scripts/rollback-ota.sh" "$@" > "$T/rb.out" 2>&1
}
RB_LIST='{"name":"production","currentPage":[
 {"group":"g-new","runtimeVersion":"rt2","platforms":"android, ios","isRollBackToEmbedded":false,"message":"bad release"},
 {"group":"g-old","runtimeVersion":"rt2","platforms":"android, ios","isRollBackToEmbedded":false,"message":"good"},
 {"group":"g-rt1","runtimeVersion":"rt1","platforms":"ios","isRollBackToEmbedded":false,"message":"older runtime"}]}'
check "rollback: plan mode names the newest group and never calls update:rollback" \
  "_rb '$RB_LIST' && grep -q 'g-new' '$T/rb.out' && ! grep -q 'update:rollback' '$T/rb.log' && grep -q 'update:list --branch production --json --non-interactive' '$T/rb.log'"
check "rollback: --yes runs update:rollback <newest group> non-interactively" \
  "_rb '$RB_LIST' --yes -m 'crash on launch' && grep -qx 'update:rollback g-new --non-interactive --platform all --message crash on launch' '$T/rb.log'"
check "rollback: --runtime picks that runtime's latest group" \
  "_rb '$RB_LIST' --runtime rt1 --yes && grep -q '^update:rollback g-rt1 ' '$T/rb.log'"
refuses "rollback: refuses when the latest update is already a rollback to embedded" \
  "_rb '{\"currentPage\":[{\"group\":\"g-e\",\"runtimeVersion\":\"rt2\",\"isRollBackToEmbedded\":true}]}' --yes"
refuses "rollback: refuses an empty branch" "_rb '{\"currentPage\":[]}' --yes"
refuses "rollback: refuses an unknown platform" "_rb '$RB_LIST' --platform web --yes"
