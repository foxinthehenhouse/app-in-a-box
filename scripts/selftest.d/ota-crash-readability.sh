# Readable OTA crashes + staged rollout: sourced by selftest.sh with $KIT, $APP, $T and
# the check/refuses helpers. Every OTA job uploads Sentry source maps, production OTAs
# start staged and reach 100% only through an approval, previews never stage, and
# scripts/rollback-ota.sh reverts a rollout in progress instead of publishing over it.
# Each rule is proven to pass on the rendered app and FAIL on a planted violation.
# (The app's jest tests for Sentry's release/dist and the request timeout run in
# `npm run gates`, under --mobile.)
echo "OTA crash readability"

OTA_PY="$APP/.venv/bin/python"
OTA_WF=mobile/.eas/workflows

# _ota_plant <edit function> <expected message>: the workflow test must fail on it.
_ota_plant() {
  local c="$T/ota-plant" out; rm -rf "$c"; mkdir -p "$c"
  cp -R "$APP/tests" "$APP/mobile" "$c/" 2>/dev/null || return 1
  rm -rf "$c/mobile/node_modules"
  (cd "$c" && "$1") || return 1
  out=$(cd "$c" && "$OTA_PY" -m pytest -q -p no:cacheprovider tests/test_eas_workflows.py 2>&1) && return 1
  printf '%s' "$out" | grep -qF -- "$2"
}
_o_no_maps() { sed -i '/^  update_android:/,/^  approve_android_rollout:/{/upload_sentry_sourcemaps/d}' $OTA_WF/release.yml && ! grep -A12 '^  update_android:' $OTA_WF/release.yml | grep -q upload_sentry; }
_o_preview_no_maps() { sed -i '/^  update_ios:/,${/upload_sentry_sourcemaps/d}' $OTA_WF/pr-preview.yml && [ "$(grep -c upload_sentry_sourcemaps $OTA_WF/pr-preview.yml)" = 1 ]; }
_o_new_job() { printf '\n  hotfix_ota:\n    type: update\n    environment: production\n    needs: [get_ios_build]\n    params:\n      platform: ios\n      branch: production\n      rollout_percentage: 10\n' >> $OTA_WF/release.yml; }
_o_full() { sed -i '/^  update_ios:/,/^  approve_ios_rollout:/{/rollout_percentage: 10$/d}' $OTA_WF/release.yml && [ "$(grep -c 'rollout_percentage: 10$' $OTA_WF/release.yml)" = 1 ]; }
_o_no_gate() { sed -i 's/needs: \[update_android, approve_android_rollout\]/needs: [update_android]/' $OTA_WF/release.yml && grep -q 'needs: \[update_android\]$' $OTA_WF/release.yml && [ "$(grep -c 'needs: \[update_android\]' $OTA_WF/release.yml)" = 2 ]; }
_o_no_promote() { python3 -c "import yaml;p='$OTA_WF/release.yml';d=yaml.safe_load(open(p));[d['jobs'].pop(k) for k in ('promote_ios','approve_ios_rollout')];yaml.safe_dump(d,open(p,'w'),sort_keys=False)"; }
_o_staged_preview() { sed -i '0,/      upload_sentry_sourcemaps: true/s//      upload_sentry_sourcemaps: true\n      rollout_percentage: 10/' $OTA_WF/pr-preview.yml && grep -q 'rollout_percentage: 10' $OTA_WF/pr-preview.yml; }
_o_no_sentry() { printf 'stack:\n  errors: none\n' > appbox.yaml; }
_o_no_sentry_off() { _o_no_sentry && sed -i 's/upload_sentry_sourcemaps: true/upload_sentry_sourcemaps: false/' $OTA_WF/*.yml; }

check "OTA: the rendered app's workflows pass the source-map and staged-rollout rules" \
  "cd '$APP' && '$OTA_PY' -m pytest -q -p no:cacheprovider tests/test_eas_workflows.py -k 'sentry or stage'"
check "OTA: a production update without upload_sentry_sourcemaps fails" \
  "_ota_plant _o_no_maps 'release.yml:update_android: set params.upload_sentry_sourcemaps: true'"
check "OTA: a preview update without upload_sentry_sourcemaps fails" \
  "_ota_plant _o_preview_no_maps 'pr-preview.yml:update_ios: set params.upload_sentry_sourcemaps: true'"
check "OTA: a newly added update job without source maps or a promote path fails" \
  "_ota_plant _o_new_job 'release.yml:hotfix_ota: set params.upload_sentry_sourcemaps: true'"
check "OTA: a production update that ships to 100% at once fails" \
  "_ota_plant _o_full 'release.yml:update_ios: rollout_percentage None; production OTAs start staged'"
check "OTA: promoting to 100% with no approval step fails" \
  "_ota_plant _o_no_gate 'release.yml:update_android: promoted to 100% with no require-approval'"
check "OTA: a staged update nothing ever promotes fails" \
  "_ota_plant _o_no_promote 'release.yml:update_ios: no update-rollout job promotes this update'"
check "OTA: a staged PR preview (it would block the PR's next push) fails" \
  "_ota_plant _o_staged_preview 'previews ship at 100%'"
check "OTA: an app without Sentry (stack.errors: none) that still uploads fails" \
  "_ota_plant _o_no_sentry 'set params.upload_sentry_sourcemaps: false (stack.errors is not sentry)'"
_ota_ok() {  # the same copy, with the plant applied, must pass
  local c="$T/ota-ok"; rm -rf "$c"; mkdir -p "$c"
  cp -R "$APP/tests" "$APP/mobile" "$c/" && rm -rf "$c/mobile/node_modules" && (cd "$c" && "$1") \
    && (cd "$c" && "$OTA_PY" -m pytest -q -p no:cacheprovider tests/test_eas_workflows.py)
}
check "OTA: an app without Sentry passes with upload_sentry_sourcemaps: false" "_ota_ok _o_no_sentry_off"

# --- rollback-ota.sh with a staged rollout in progress (fake eas) --------------------
_ota_fake_eas() {
  local dir="$T/ota-fake-eas"; mkdir -p "$dir"
  cat > "$dir/eas" <<'SH'
#!/usr/bin/env bash
echo "$*" >> "$FAKE_EAS_LOG"
case "$1" in
  update:list) cat "$FAKE_EAS_LIST" ;;
  update:rollback|update:revert-update-rollout) echo "done" ;;
  *) exit 3 ;;
esac
SH
  chmod +x "$dir/eas"; echo "$dir/eas"
}
_ota_rb() {  # _ota_rb <list-json> <args...>  -> stdout in $T/ota-rb.out, calls in $T/ota-rb.log
  printf '%s' "$1" > "$T/ota-rb.list"; shift; : > "$T/ota-rb.log"
  EAS="$(_ota_fake_eas)" FAKE_EAS_LIST="$T/ota-rb.list" FAKE_EAS_LOG="$T/ota-rb.log" \
    bash "$APP/scripts/rollback-ota.sh" "$@" > "$T/ota-rb.out" 2>&1
}
OTA_STAGED='{"currentPage":[
 {"group":"g-staged","runtimeVersion":"rt2","platforms":"android","isRollBackToEmbedded":false,"rolloutPercentage":10,"message":"new"},
 {"group":"g-old","runtimeVersion":"rt2","platforms":"android","isRollBackToEmbedded":false,"message":"good"}]}'
OTA_DONE='{"currentPage":[
 {"group":"g-full","runtimeVersion":"rt2","platforms":"android","isRollBackToEmbedded":false,"rolloutPercentage":100,"message":"promoted"}]}'
check "OTA rollback: the plan names a rollout in progress and prints the promote command, calling nothing" \
  "_ota_rb '$OTA_STAGED' && grep -q 'in progress, at 10% of users' '$T/ota-rb.out' \
   && grep -q 'update:edit g-staged --rollout-percentage 100 --non-interactive' '$T/ota-rb.out' \
   && grep -q 'update:revert-update-rollout --group g-staged' '$T/ota-rb.out' && ! grep -qv '^update:list' '$T/ota-rb.log'"
check "OTA rollback: --yes reverts the rollout instead of publishing over it" \
  "_ota_rb '$OTA_STAGED' --yes -m 'crash spike' && grep -qx 'update:revert-update-rollout --group g-staged --non-interactive --message crash spike' '$T/ota-rb.log' && ! grep -q 'update:rollback' '$T/ota-rb.log'"
refuses "OTA rollback: refuses --platform on a rollout (it reverts as a whole group)" \
  "_ota_rb '$OTA_STAGED' --platform ios --yes || { cat '$T/ota-rb.out'; false; }" "drop --platform"
check "OTA rollback: a rollout already at 100% rolls back like any update" \
  "_ota_rb '$OTA_DONE' --yes && grep -q '^update:rollback g-full --non-interactive' '$T/ota-rb.log'"

# --- the app side: Sentry release/dist and the request timeout ----------------------
check "OTA: monitoring and the request timeout have jest tests, and monitoring is off the no-test list" \
  "[ -f '$APP/mobile/lib/__tests__/monitoring.test.ts' ] && [ -f '$APP/mobile/lib/__tests__/api-timeout.test.ts' ] \
   && ! grep -q '\"lib/monitoring\"' '$APP/mobile/scripts/check-test-presence.js'"
check "OTA: the ship skill documents the crash-free promote gate" \
  "grep -q 'promote the staged rollout' '$APP/.agents/skills/ship/SKILL.md' && grep -q '99.5%' '$APP/.agents/skills/ship/SKILL.md' && grep -q '99.5%' '$APP/docs/runbooks/release.md'"
