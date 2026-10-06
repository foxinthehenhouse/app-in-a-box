# Guardrail packs (trust by default): sourced by scripts/selftest.sh with $KIT, $APP (the
# rendered app, a git repo on a feature branch, cwd), $T and the check/refuses helpers.
#
# The generated app enforces privacy and safety in code: scripts/check_guardrails.py
# (CI's python job) reads the packs from privacy/data-map.yaml and runs each enabled
# pack's checks; Semgrep scans the backend (security.yml); a path rule speaks up when a
# migration adds a personal-looking column. Each guard is proven here to pass on the
# pristine render AND to fail on a planted violation, naming its rule; and a pack that is
# off is proven to cost nothing (the same plant passes until the pack is turned on).
# Every plant is reverted. With --mobile, `npm run gates` also runs with every pack on.

GP_PY="$APP/.venv/bin/python"
GP_PT="$GP_PY -m pytest -q -p no:cacheprovider -p no:warnings"
GP_MAP=privacy/data-map.yaml

_gp_fails_with() {  # NAME CMD NEEDLE: CMD fails AND names the rule
  local out
  if out="$(eval "$2" 2>&1)"; then bad "$1 (still green)"; return; fi
  if grep -qF -- "$3" <<<"$out"; then ok "$1"; else bad "$1 (failed, but not on: $3)"; printf '%s\n' "$out" | tail -8 | sed 's/^/        | /'; fi
}
# Every file a plant below may touch; saved before and restored after each plant.
GP_FILES=("$GP_MAP" mobile/lib/packs.ts mobile/lib/analytics.ts mobile/app.json "mobile/app/(auth)/sign-in.tsx")
_gp_save() {
  mkdir -p "$T/gp"
  local f k
  for f in "${GP_FILES[@]}"; do
    k="$T/gp/$(echo "$f" | tr '/()' '___')"
    rm -f "$k" "$k.absent"
    if [ -f "$f" ]; then cp "$f" "$k"; else : > "$k.absent"; fi
  done
}
_gp_restore() {
  local f k
  for f in "${GP_FILES[@]}"; do
    k="$T/gp/$(echo "$f" | tr '/()' '___')"
    if [ -f "$k.absent" ]; then rm -f "$f"; rmdir "$(dirname "$f")" 2>/dev/null || true; else cp "$k" "$f"; fi
  done
}
# _gp_packs <pack...>: set the data map's packs (keeping the rest of it) and sync
# mobile/lib/packs.ts, as the scaffold does.
_gp_packs() {
  python3 - "$GP_MAP" "$@" <<'PYEOF' && python3 scripts/check_guardrails.py --write >/dev/null
import os, sys, yaml
path, packs = sys.argv[1], sys.argv[2:]
data = yaml.safe_load(open(path)) if os.path.exists(path) else {}
data = data if isinstance(data, dict) else {}
data["packs"] = packs
os.makedirs(os.path.dirname(path), exist_ok=True)
yaml.safe_dump(data, open(path, "w"), sort_keys=False)
PYEOF
}

check "guardrails: clean on the pristine render (baseline only)" "python3 scripts/check_guardrails.py"
check "guardrails: the app's own tests pass (a planted control per rule, per pack)" "$GP_PT tests/test_guardrails.py"
check "guardrails: clean with EVERY pack on (the template already meets each one)" \
  "_gp_save && _gp_packs location minors health ugc financial biometric && python3 scripts/check_guardrails.py; rc=\$?; _gp_restore; exit \$rc"

# baseline
_gp_save
sed -i.x 's/^  updatePrompted: () =>/  invited: (p: { email: string }) => capture("invited", p),\n  updatePrompted: () =>/' mobile/lib/analytics.ts && rm -f mobile/lib/analytics.ts.x
_gp_fails_with "guardrails catch: an email in an analytics payload" \
  "python3 scripts/check_guardrails.py" "[baseline] mobile/lib/analytics.ts:"
_gp_restore
printf 'import { analytics } from "./analytics";\nexport const planted = (pos: { coords: { latitude: number } }) => analytics.screenViewed("map", { lat: pos.coords.latitude });\n' > mobile/lib/planted.ts
_gp_fails_with "guardrails catch: a precise location passed to analytics.*" \
  "python3 scripts/check_guardrails.py" "\`lat\` passed to analytics looks like a precise location"
printf 'import { posthog } from "./analytics";\nexport const planted = () => posthog?.capture("x", {});\n' > mobile/lib/planted.ts
_gp_fails_with "guardrails catch: PostHog called around lib/analytics.ts" \
  "python3 scripts/check_guardrails.py" "posthog.capture() called directly"
rm -f mobile/lib/planted.ts
printf 'import logging\n\nlogger = logging.getLogger(__name__)\n\n\ndef planted(user):\n    logger.info("signed up %%s", user.email)\n' > backend/services/planted.py
_gp_fails_with "guardrails catch: an email in a backend log call" \
  "python3 scripts/check_guardrails.py" "planted.py:7: \`email\` logged"
rm -f backend/services/planted.py

# off costs nothing, on enforces
_gp_save
sed -i.x 's/^  updatePrompted: () =>/  checkedIn: (p: { heart_rate: number }) => capture("checked_in", p),\n  updatePrompted: () =>/' mobile/lib/analytics.ts && rm -f mobile/lib/analytics.ts.x
check "guardrails: a pack that is off costs nothing (heart_rate passes with health off)" "python3 scripts/check_guardrails.py"
_gp_packs health
_gp_fails_with "guardrails catch: heart_rate in analytics once the health pack is on" \
  "python3 scripts/check_guardrails.py" "[health] mobile/lib/analytics.ts:"
_gp_restore

# location
_gp_save
_gp_packs location
python3 -c "import json;p='mobile/app.json';d=json.load(open(p));d['expo']['ios']['infoPlist']={'UIBackgroundModes':['location']};json.dump(d,open(p,'w'))"
_gp_fails_with "guardrails catch: background location with no declared reason (location pack)" \
  "python3 scripts/check_guardrails.py" "[location] background location is requested (ios.infoPlist.UIBackgroundModes)"
_gp_restore
_gp_save
_gp_packs location
printf -- '-- Rollback: drop table public.check_ins;\ncreate table public.check_ins (id uuid primary key, latitude double precision);\n' > supabase/migrations/20990101000000_planted.sql
_gp_fails_with "guardrails catch: a location table the prune cron never expires" \
  "python3 scripts/check_guardrails.py" "table \`check_ins\` stores location (latitude) but has no TTL"
rm -f supabase/migrations/20990101000000_planted.sql
_gp_restore

# minors
_gp_save
_gp_packs minors
sed -i.x 's|<AgeGate status={age} onDone={setAge} />|{null}|' "mobile/app/(auth)/sign-in.tsx" && rm -f "mobile/app/(auth)/sign-in.tsx.x"
_gp_fails_with "guardrails catch: the age gate unmounted (minors pack)" \
  "python3 scripts/check_guardrails.py" "[minors] no screen under mobile/app/ renders <AgeGate>"
_gp_restore

# ugc, financial, biometric
_gp_save
_gp_packs ugc financial biometric
printf -- '-- Rollback: drop table public.posts;\ncreate table public.posts (\n  id uuid primary key,\n  body text not null,\n  tip_amount real,\n  author_faceprint bytea\n);\n' > supabase/migrations/20990101000000_planted.sql
_gp_fails_with "guardrails catch: user content with no report/block (App Store 1.2, ugc pack)" \
  "python3 scripts/check_guardrails.py" "[ugc] user content in \`posts\`, but no reports table"
_gp_fails_with "guardrails catch: a floating-point money column (financial pack)" \
  "python3 scripts/check_guardrails.py" "[financial] supabase/migrations/20990101000000_planted.sql:5: money column \`tip_amount\` is real"
_gp_fails_with "guardrails catch: a stored biometric template (biometric pack)" \
  "python3 scripts/check_guardrails.py" "[biometric] supabase/migrations/20990101000000_planted.sql: \`posts.author_faceprint\`"
rm -f supabase/migrations/20990101000000_planted.sql
_gp_restore

# the migration hook: content-aware, so it speaks only for a personal-looking column
_gp_hook() {  # <sql> -> the hook's output for writing it into a migration
  python3 -c "import json,sys; print(json.dumps({'tool_input': {'file_path': sys.argv[1] + '/supabase/migrations/x.sql', 'content': sys.argv[2]}, 'session_id': 'gp' + sys.argv[3]}))" \
    "$APP" "$1" "$RANDOM$RANDOM" | CLAUDE_PROJECT_DIR="$APP" python3 .claude/hooks/inject-path-rules.py
}
check "privacy rule injected when a migration adds a personal-looking column" \
  "_gp_hook 'alter table public.profiles add column birth_date date;' | grep -q 'privacy-columns.md.*birth_date date'"
refuses "privacy rule stays quiet for a column that isn't personal" \
  "_gp_hook 'alter table public.profiles add column streak_days int;' | grep -q privacy-columns.md"

# Semgrep: pinned in its own hashed lock; its rule tests and the scan, and a planted eval.
GP_SG="$T/semgrep-venv"
if [ -x /root/.local/bin/uv ] || command -v uv >/dev/null 2>&1; then GP_UV="$(command -v uv || echo /root/.local/bin/uv)"; else GP_UV=""; fi
if { [ -n "$GP_UV" ] && "$GP_UV" venv -q -p 3.12 "$GP_SG" >/dev/null 2>&1 && "$GP_UV" pip install -q --python "$GP_SG/bin/python" --require-hashes -r requirements-semgrep.lock >/dev/null 2>&1; } \
   || { python3 -m venv "$GP_SG" >/dev/null 2>&1 && "$GP_SG/bin/python" -m pip install -q --require-hashes -r requirements-semgrep.lock >/dev/null 2>&1; }; then
  GP_SEMGREP="$GP_SG/bin/semgrep"
  check "semgrep: every rule's own test cases pass (pinned, from requirements-semgrep.lock)" \
    "'$GP_SEMGREP' --test --metrics=off --disable-version-check --config .semgrep/backend.yml .semgrep/backend.py"
  check "semgrep: the pristine backend scans clean" \
    "'$GP_SEMGREP' scan --config .semgrep/backend.yml --error --metrics=off --disable-version-check --quiet backend"
  printf 'def planted(expr: str) -> object:\n    return eval(expr)\n' > backend/services/planted.py
  _gp_fails_with "semgrep catches a planted eval() in the backend" \
    "'$GP_SEMGREP' scan --config .semgrep/backend.yml --error --metrics=off --disable-version-check backend" "no-eval-exec"
  rm -f backend/services/planted.py
else
  skip "semgrep: rule tests, clean scan, planted eval" "uv or pip with registry access (requirements-semgrep.lock)"
fi

check "guardrails: every plant was reverted" \
  "[ -z \"\$(git status --porcelain -- mobile backend supabase privacy)\" ]"

# With --mobile: the real Expo app's gates (tsc, eslint, jest incl. the age gate and the
# scrubbers) pass with EVERY pack on, so turning a pack on never breaks the build.
mobile_check_guardrail_packs() {
  local root; root="$(cd .. && pwd)"
  ( cd "$root" && _gp_save && _gp_packs location minors health ugc financial biometric )
  check "npm run gates green with every guardrail pack on" "grep -q '\"minors\"' lib/packs.ts && npm run -s gates"
  ( cd "$root" && _gp_restore && python3 scripts/check_guardrails.py >/dev/null )
}
