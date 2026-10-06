# Architecture boundaries as checks: sourced by selftest.sh with $KIT, $APP, $T and the
# check/refuses/skip helpers. The prose rules in the app's AGENTS.md ("backend computes",
# routers do I/O and services hold logic, the LLM is fenced) are enforced twice:
#   lint-imports           pyproject.toml [tool.importlinter]: layers + an SDK fence (CI python job)
#   eslint.boundaries.js   mobile/: fetch only in lib/api.ts, no Supabase in app/, no
#                          lib/api in components/ui (spread into eslint.config.js -> npm run gates)
# Each passes on the pristine render and FAILS on a planted violation, naming the rule.
# Plants run on copies under $T, so $APP is never touched.
#
# Where things run: the Python side uses the app's own dev venv (built by "pytest green",
# so import-linter comes from requirements-dev.txt). The mobile plants need only eslint
# and the TypeScript parser, installed into $T from npm; they lint with the boundaries
# file alone. The full Expo config (eslint-config-expo + boundaries) is proven green on
# the pristine app by `npm run gates` under --mobile.

AB_LINT="$APP/.venv/bin/lint-imports"

# ---- Python: import-linter ---------------------------------------------------------------
_ab_py_copy() {  # a fresh copy of the app's backend + pyproject at $T/ab-py
  rm -rf "$T/ab-py" && mkdir -p "$T/ab-py" && cp -R "$APP/backend" "$APP/pyproject.toml" "$T/ab-py/"
}
_ab_lint() { (cd "$T/ab-py" && "$AB_LINT" --no-cache 2>&1); }

if [ -x "$AB_LINT" ]; then
  check "boundaries: lint-imports keeps both contracts on the pristine app" \
    "_ab_py_copy && _ab_lint | grep -q 'Contracts: 2 kept, 0 broken'"
  check "boundaries: the app's CI python job runs lint-imports, pinned in requirements-dev" \
    "grep -q 'run: lint-imports' '$APP/.github/workflows/ci.yml' && grep -qE '^import-linter>=[0-9.]+,<[0-9]' '$APP/requirements-dev.txt'"
  check "boundaries: test_guards_wired.py fails if the contracts are weakened (its negative controls)" \
    "cd '$APP' && ./.venv/bin/python -m pytest -q -p no:warnings tests/harness/test_guards_wired.py -k 'boundaries or mobile_gates'"

  _ab_py_copy && printf '\nfrom backend.routers import me  # noqa: E402,F401\n' >> "$T/ab-py/backend/services/jobs_service.py"
  refuses "boundaries catch: a service importing a router (layers contract)" "_ab_lint" \
    "backend.services is not allowed to import backend.routers"
  _ab_py_copy && printf 'from backend.routers import me  # noqa: F401\n' > "$T/ab-py/backend/db_helpers.py" \
    && printf '\nfrom backend import db_helpers  # noqa: E402,F401\n' >> "$T/ab-py/backend/config.py"
  refuses "boundaries catch: config reaching a router through an unlisted helper (indirect)" "_ab_lint" \
    "backend.config is not allowed to import backend.routers"
  _ab_py_copy && printf 'import anthropic  # noqa: F401\n' > "$T/ab-py/backend/routers/summary.py"
  refuses "boundaries catch: an anthropic import outside the AI fence" "_ab_lint" \
    "backend is not allowed to import anthropic"
  _ab_py_copy && printf 'from openai import OpenAI  # noqa: F401\n' > "$T/ab-py/backend/services/suggest.py"
  refuses "boundaries catch: an openai import in a service that isn't the fenced module" "_ab_lint" \
    "backend is not allowed to import openai"
  # The recipe-ai-feature path: the one fenced module, listed in ignore_imports, passes.
  # Its callers stay clean too, since the ignored edge is the only way to the SDK.
  _ab_fence() {
    _ab_py_copy || return 1
    printf 'import anthropic  # noqa: F401\n' > "$T/ab-py/backend/services/ai_summary.py"
    printf 'from backend.services import ai_summary  # noqa: F401\n' > "$T/ab-py/backend/routers/summary.py"
    sed -i.bak 's|^ignore_imports = \[\]$|ignore_imports = ["backend.services.ai_summary -> anthropic"]|' "$T/ab-py/pyproject.toml"
    grep -q 'ai_summary -> anthropic' "$T/ab-py/pyproject.toml" || { echo "fence line not planted"; return 1; }
    _ab_lint | grep -q 'Contracts: 2 kept, 0 broken'
  }
  check "boundaries allow: the recipe's fenced module (backend/services/ai_<feature>.py) once listed" "_ab_fence"
  _ab_fence >/dev/null 2>&1; rm -f "$T/ab-py/backend/services/ai_summary.py" "$T/ab-py/backend/routers/summary.py"
  refuses "boundaries catch: a stale fence entry that matches no import" "_ab_lint" \
    "No matches for ignored import backend.services.ai_summary -> anthropic"
else
  bad "boundaries: lint-imports not in the app venv (requirements-dev.txt; built by 'pytest green')"
fi

# ---- Mobile: eslint core rules -----------------------------------------------------------
AB_ES="$T/ab-eslint"
_ab_es_install() {
  mkdir -p "$AB_ES" && cd "$AB_ES" && printf '{"private":true}\n' > package.json \
    && npm install --no-audit --no-fund --loglevel=error "eslint@^9" "@typescript-eslint/parser@^8" >/dev/null 2>&1
}
if command -v npm >/dev/null 2>&1 && (_ab_es_install); then
  # A copy of the rendered app's source with a minimal config: the TS parser + the
  # boundaries file, nothing else (inline disables for Expo's rules are ignored).
  _ab_mob_copy() {
    local c="$T/ab-mob"; rm -rf "$c"; mkdir -p "$c"
    (cd "$APP/mobile" && tar --exclude=node_modules -cf - app components lib eslint.boundaries.js) | (cd "$c" && tar -xf -) || return 1
    cat > "$c/eslint.config.js" <<'JSEOF'
const parser = require("@typescript-eslint/parser");
module.exports = [
  { files: ["**/*.ts", "**/*.tsx"], languageOptions: { parser, parserOptions: { ecmaFeatures: { jsx: true } } } },
  ...require("./eslint.boundaries.js"),
];
JSEOF
  }
  _ab_eslint() { (cd "$T/ab-mob" && NODE_PATH="$AB_ES/node_modules" "$AB_ES/node_modules/.bin/eslint" --no-inline-config . 2>&1); }
  # <file under mobile/> <contents>: plant one violation in a fresh copy
  _ab_plant() { _ab_mob_copy && mkdir -p "$(dirname "$T/ab-mob/$1")" && printf "$2" > "$T/ab-mob/$1"; }

  check "boundaries: the app's eslint.config.js spreads eslint.boundaries.js" \
    "grep -q 'require(\"./eslint.boundaries.js\")' '$APP/mobile/eslint.config.js' && grep -q '\.\.\.boundaries' '$APP/mobile/eslint.config.js'"
  check "boundaries: the pristine app's app/, components/ and lib/ pass" "_ab_mob_copy && _ab_eslint"
  _ab_plant 'app/(app)/planted.tsx' 'export async function load() {\n  const r = await fetch("https://example.com/x");\n  return r.json();\n}\n'
  refuses "boundaries catch: a fetch call in a screen" "_ab_eslint" "Only lib/api.ts calls fetch"
  _ab_plant 'components/Planted.tsx' 'export const load = () => globalThis.fetch("/x");\n'
  refuses "boundaries catch: globalThis.fetch outside lib/api.ts" "_ab_eslint" "'globalThis.fetch' is restricted"
  _ab_plant 'app/(app)/planted.tsx' 'import { supabase } from "../../lib/supabase";\nexport const s = supabase;\n'
  refuses "boundaries catch: a screen importing lib/supabase" "_ab_eslint" "Screens don't import lib/supabase"
  _ab_plant 'app/planted.tsx' 'import { createClient } from "@supabase/supabase-js";\nexport const c = createClient;\n'
  refuses "boundaries catch: a screen importing supabase-js directly" "_ab_eslint" "Screens don't talk to Supabase"
  _ab_plant 'components/ui/Planted.tsx' 'import { getMe } from "../../lib/api";\nexport const m = getMe;\n'
  refuses "boundaries catch: components/ui importing lib/api" "_ab_eslint" "components/ui is presentation"
else
  skip "boundaries: mobile eslint plants" "npm with registry access (eslint + @typescript-eslint/parser)"
fi
cd "$APP"
