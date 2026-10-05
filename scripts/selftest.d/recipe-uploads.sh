# recipe-uploads (opt-in image uploads): sourced by selftest.sh with $KIT, $APP, $T and
# the check/refuses/skip helpers. The recipe ships code, so it is proven like template
# code: apply it to a COPY of the rendered app, run that app's own tests and guards, and
# plant each mistake the tests exist to catch. $APP itself is never touched.
#
# With APPBOX_SELFTEST_DATABASE_URL (a throwaway Postgres + pgTAP, as trust.sh) the
# applied app's DB gate runs in its own fresh database, and the bucket policies are
# re-opened one half at a time: the pgTAP suite must fail on each. Under --mobile,
# mobile_check_recipe_uploads (below) installs expo-image-picker into the real Expo app,
# applies the recipe and runs `npm run gates`.
RU="$KIT/skills/recipe-uploads"
RU_APP="$T/ru-app"
RU_PY="$APP/.venv/bin/python"
RU_PT="$RU_PY -m pytest -q -p no:cacheprovider -p no:warnings"

# ---- the skill's shape --------------------------------------------------------------------

_ru_shape() {
  local f="$RU/SKILL.md" h
  [ "$(sed -n 2p "$f")" = "name: recipe-uploads" ] && grep -q '^description: .*upload' "$f" || { echo "frontmatter"; return 1; }
  for h in '## What it adds' '## Steps' '## Env / wiring checklist' '## Egress costs, and when to move to Cloudflare R2' \
           '## Tests it ships (keep them green)' '## Done means'; do
    grep -qxF "$h" "$f" || { echo "missing section: $h"; return 1; }
  done
  grep -q '⚖️ Owner decisions' "$f" && grep -q 'plugin root' "$f" && grep -q '\- \[ \] ' "$f"
}
check "recipe-uploads: SKILL.md has the recipe shape (owner calls, steps, wiring, egress/R2 note, done-means)" _ru_shape

_ru_files_named() {  # every shipped file is named in SKILL.md; every edited file exists in the template
  local p bad=0
  while IFS= read -r p; do
    p="${p#"$RU/files/"}"; p="${p/TIMESTAMP_/<now>_}"
    grep -qF "$(basename "$p")" "$RU/SKILL.md" || { echo "not named in SKILL.md: $p"; bad=1; }
  done < <(find "$RU/files" -type f | sort)
  while IFS= read -r p; do
    [ -f "$APP/$p" ] || { echo "apply.py edits a file the template doesn't have: $p"; bad=1; }
  done < <(python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('ru_apply', '$RU/apply.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('\n'.join(p for p, _, _ in m.EDITS))")
  ! grep -rIl '__APP_\|__BUNDLE_ID__\|__OWNER__\|__SCHEME__' "$RU" || { echo "template placeholders in the recipe (it is applied to a rendered app)"; bad=1; }
  [ "$bad" = 0 ]
}
check "recipe-uploads: every shipped file is named in SKILL.md, every edited file exists, no placeholders" _ru_files_named

check "recipe-uploads: expo-image-picker is installed by the recipe, never by mobile-deps.sh" \
  "! grep -q 'expo-image-picker' '$KIT/scripts/mobile-deps.sh' && grep -q 'npx expo install expo-image-picker' '$RU/SKILL.md'"
check "recipe-uploads: listed as a recipe in PRODUCTION.md, with should-fire and shouldn't-fire evals" \
  "grep -q '| Recipe | \`recipe-uploads\`' '$KIT/docs/PRODUCTION.md' \
   && grep -q 'input_match: recipe-uploads' '$KIT'/evals/*-recipe-uploads-fires/graders/*.md \
   && grep -A3 'input_match: recipe-uploads' '$KIT'/evals/*-recipe-uploads-stays-quiet/graders/*.md | grep -q 'max: 0'"

# ---- applied to a copy of the app ---------------------------------------------------------

_ru_copy() {  # _ru_copy <dir>: the rendered app without git history or node_modules
  rm -rf "$1" && mkdir -p "$1"
  (cd "$APP" && tar --exclude=node_modules --exclude=.git -cf - .) | (cd "$1" && tar -xf -)
}
_ru_applied() {
  _ru_copy "$RU_APP" || return 1
  python3 "$RU/apply.py" "$RU_APP" > "$T/ru-apply.out" || { cat "$T/ru-apply.out"; return 1; }
  grep -q 'edited: backend/routers/me.py' "$T/ru-apply.out" && grep -q 'added: backend/routers/uploads.py' "$T/ru-apply.out" \
    && ls "$RU_APP"/supabase/migrations/2*_uploads.sql >/dev/null || return 1
  # Idempotent: a second run copies and edits nothing.
  python3 "$RU/apply.py" "$RU_APP" > "$T/ru-apply2.out" && ! grep -qE 'added|edited' "$T/ru-apply2.out" \
    && [ "$(ls "$RU_APP"/supabase/migrations/*_uploads.sql | wc -l)" -eq 1 ]
}
check "recipe-uploads: apply.py applies cleanly to a rendered app, and a second run changes nothing" _ru_applied
check "recipe-uploads: the applied app's pytest is green (uploads, export, deletion, wire contract, scoping, AGENTS.md map)" \
  "cd '$RU_APP' && $RU_PT"
check "recipe-uploads: the applied app is ruff + pyright clean" \
  "cd '$RU_APP' && '$APP/.venv/bin/ruff' check backend tests scripts && PATH='$APP/.venv/bin':\$PATH pyright"
check "recipe-uploads: the applied app's mobile guards pass (analytics coverage, test presence, strings, design, Maestro)" \
  "cd '$RU_APP/mobile' && node scripts/check-analytics-coverage.js && node scripts/check-test-presence.js \
   && node scripts/check-hardcoded-strings.js && node scripts/check-design-tells.js && node scripts/check-maestro-coverage.js \
   && node scripts/check-eas-shipping-env.js"

_ru_refuses_anchor() {  # an app whose me.py was reworked: nothing written, the edit named
  local c="$T/ru-anchor"
  _ru_copy "$c" || return 1
  sed -i.bak 's/^def _delete_user_files(db: Any, user_id: str) -> None:/def _purge(db: Any, user_id: str) -> None:/' "$c/backend/routers/me.py" && rm -f "$c/backend/routers/me.py.bak"
  python3 "$RU/apply.py" "$c" > "$T/ru-anchor.out" 2>&1 && return 1
  grep -q 'nothing written' "$T/ru-anchor.out" && grep -q 'backend/routers/me.py: call `uploads_service.delete_user_files' "$T/ru-anchor.out" \
    && [ ! -e "$c/backend/routers/uploads.py" ] && ! grep -q uploads "$c/backend/main.py"
}
check "recipe-uploads: apply.py writes nothing and names the edit when an app reworked a file it edits" _ru_refuses_anchor

_ru_older_app() {  # an app rendered before the kit stubbed Storage gets the stub and the fake
  local c="$T/ru-old"
  _ru_copy "$c" || return 1
  python3 - "$c" <<'PY' || return 1
import pathlib, re, sys
c = pathlib.Path(sys.argv[1])
stubs = c / "supabase/ci/platform_stubs.sql"
stubs.write_text(stubs.read_text().split("\n-- Storage:")[0] + "\n")
fakes = c / "tests/test_prod_fakes.py"
s = fakes.read_text()
s = s[: s.index("class FakeBucket:")] + s[s.index("class FakeDB:") :]
s = s.replace("        self.storage = FakeStorage()\n", "")
s = re.sub(r"\ndef test_fake_storage_lists_only.*?(?=\ndef )", "\n", s, flags=re.S)
fakes.write_text(s)
PY
  python3 "$RU/apply.py" "$c" > "$T/ru-old.out" || { cat "$T/ru-old.out"; return 1; }
  grep -q 'create schema if not exists storage' "$c/supabase/ci/platform_stubs.sql" \
    && (cd "$c" && $RU_PT tests/test_uploads.py tests/test_prod_account_deletion.py tests/test_v1_export.py)
}
check "recipe-uploads: on an app made before Storage was stubbed, apply.py adds the stub + the fake and the tests pass" _ru_older_app

# ---- negative controls: each planted mistake must fail the applied app's tests ------------------

# name, file (relative to the applied app), sed expression, test target, needle
_ru_plant() {
  local f="$RU_APP/$2"
  cp "$f" "$T/ru-plant.bak"
  sed -i.sedbak "$3" "$f" && rm -f "$f.sedbak"
  if cmp -s "$T/ru-plant.bak" "$f"; then
    bad "$1 (planted change did not apply; update recipe-uploads.sh)"
  else
    refuses "$1" "cd '$RU_APP' && $4" "$5"
  fi
  cp "$T/ru-plant.bak" "$f"
}
if [ -f "$RU_APP/backend/routers/uploads.py" ]; then
  _ru_plant "recipe-uploads: tests fail when the list drops its user filter (another user's files leak)" \
    backend/services/uploads_service.py '/def list_uploads/,/execute/ s/\.eq("user_id", user_id)//' \
    "$RU_PT tests/test_uploads.py" "test_list_returns_only_the_callers_uploads"
  _ru_plant "recipe-uploads: tests fail when account deletion stops emptying the folder" \
    backend/routers/me.py '/^    uploads_service.delete_user_files(db, user_id)$/d' \
    "$RU_PT tests/test_uploads.py" "test_account_deletion_empties_the_callers_folder_first"
  _ru_plant "recipe-uploads: tests fail when a rejected object is left in Storage" \
    backend/services/uploads_service.py '/landed, but too big/,+1 s/_bucket(db).remove(\[object_path(user_id, upload_id)\])/pass/' \
    "$RU_PT tests/test_uploads.py" "test_complete_rejects_and_removes_what_should_never_have_landed"
  _ru_plant "recipe-uploads: tests fail when minting upload URLs loses its rate limit" \
    backend/routers/uploads.py 's/dependencies=\[Depends(rate_limit("uploads.create", 20))\],//' \
    "$RU_PT tests/test_uploads.py" "test_every_upload_route_is_rate_limited"
  _ru_plant "recipe-uploads: tests fail when the export reader drops its user filter" \
    backend/routers/export.py '/def _read_uploads/,/execute/ s/\.eq("user_id", user_id)//' \
    "$RU_PT tests/test_uploads.py tests/test_v1_export.py" "test_export_lists_the_callers_files_with_download_links"
  _ru_plant "recipe-uploads: tests fail when the bucket's size limit and the API's disagree" \
    "$(cd "$RU_APP" && ls supabase/migrations/*_uploads.sql)" "s/'uploads', 'uploads', false, 10485760/'uploads', 'uploads', false, 52428800/" \
    "$RU_PT tests/test_uploads.py" "test_bucket_limits_match_the_api"
  _ru_plant "recipe-uploads: the wire contract fails when UploadWire drifts from the model" \
    mobile/lib/api.ts 's/^  downloadUrl: string;/  downloadURL: string;/' \
    "$RU_PT tests/test_wire_contract.py" "UploadWire"
  _ru_plant "recipe-uploads: the analytics guard fails when the upload event loses its call site" \
    mobile/lib/uploads.ts 's/analytics\.imageUploaded(/void (/' \
    "node mobile/scripts/check-analytics-coverage.js" "dead helper: analytics.imageUploaded"
  check "recipe-uploads: every plant was reverted (the applied app is green again)" \
    "cd '$RU_APP' && $RU_PT tests/test_uploads.py tests/test_wire_contract.py tests/test_v1_export.py && node mobile/scripts/check-analytics-coverage.js"
else
  bad "recipe-uploads: negative controls (the recipe did not apply, see above)"
fi

# ---- the database: the real policies against a real Postgres -------------------------------------

_ru_tap() {  # _ru_tap <db url> <plant sql>: the uploads pgTAP file with one policy re-opened
  { echo "begin;"; printf '%s\n' "$2"; cat "$RU_APP/supabase/tests/database/uploads.test.sql"; } \
    | psql "$1" -X -q -tA -v ON_ERROR_STOP=0 2>&1
}
_ru_db() {
  local base="$APPBOX_SELFTEST_DATABASE_URL" name="appbox_ru_$$" url out
  url="${base%/*}/$name"; case "$base" in *\?*) url="${base%%\?*}"; url="${url%/*}/$name?${base#*\?}" ;; esac
  psql "$base" -X -q -c "drop database if exists $name" -c "create database $name" || return 1
  # --write-snapshot: the skill refreshes supabase/schema-snapshot.txt with the migration.
  out=$(cd "$RU_APP" && DATABASE_URL="$url" ./scripts/db-test.sh --write-snapshot 2>&1); local rc=$?
  printf '%s\n' "$out" | grep -E 'pgTAP|caught|db-test|not ok|ERROR' | head -20
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q '# supabase/tests/database/uploads.test.sql'; then
    # Each half of the select policy, removed on its own, must turn the suite red.
    _ru_tap "$url" "drop policy \"uploads_select_own\" on storage.objects; create policy \"uploads_select_own\" on storage.objects for select to authenticated using (bucket_id = 'uploads');" > "$T/ru-tap1.out"
    _ru_tap "$url" "drop policy \"uploads_select_own\" on storage.objects; create policy \"uploads_select_own\" on storage.objects for select to authenticated using ((storage.foldername(name))[1] = (select auth.uid())::text);" > "$T/ru-tap2.out"
    grep -q "^not ok .* - a user cannot read another user's file" "$T/ru-tap1.out" \
      && grep -q "^not ok .* - the policies do not reach another bucket" "$T/ru-tap2.out" \
      || { echo "pgTAP stayed green with a policy half removed:"; cat "$T/ru-tap1.out" "$T/ru-tap2.out" | grep -E '^(not )?ok|ERROR' | head -30; rc=1; }
  else
    rc=1
  fi
  psql "$base" -X -q -c "drop database if exists $name" >/dev/null 2>&1
  return "$rc"
}
if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ] && [ -f "$RU_APP/backend/routers/uploads.py" ]; then
  check "recipe-uploads: DB gate green with the recipe (bucket, policies, record_upload) and pgTAP fails on each re-opened policy half" _ru_db
else
  skip "recipe-uploads: DB gate with the recipe + pgTAP negative controls on the bucket policies" "APPBOX_SELFTEST_DATABASE_URL (Postgres + pgTAP)"
fi

# ---- --mobile: the recipe in the real Expo app ---------------------------------------------------
# Called by selftest.sh after the template's own mobile checks (cwd: the Expo app's mobile/).
# It changes that app (installs a package, applies the recipe); nothing runs after it.
mobile_check_recipe_uploads() {
  local mob="$PWD"
  if (npx expo install expo-image-picker || EXPO_OFFLINE=1 npx expo install expo-image-picker) >/dev/null 2>&1 \
     && python3 "$RU/apply.py" "$(dirname "$mob")" >/dev/null; then
    check "recipe-uploads: npm run gates green with the recipe applied (tsc, eslint, guards, its jest tests, coverage floor)" \
      "cd '$mob' && npm run -s gates"
  else
    bad "recipe-uploads: install expo-image-picker + apply the recipe in the real Expo app"
  fi
}
