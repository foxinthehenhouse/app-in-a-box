# Maestro: the MCP is registered for both agents, every route has a flow
# (and the coverage lint fails when one goes missing), flows parse, and the flows EAS
# runs never depend on demo mode (which a release build doesn't have).

MAE="$APP/mobile"
check "Maestro MCP registered in .mcp.json and mirrored to Codex" \
  "python3 -c \"import json,tomllib; m=json.load(open('$APP/.mcp.json'))['mcpServers']['maestro']; assert m=={'command':'maestro','args':['mcp']}; c=tomllib.load(open('$APP/.codex/config.toml','rb'))['mcp_servers']['maestro']; assert c['command']=='maestro' and c['args']==['mcp']\""
check "maestro coverage: every route has a flow, every flow id is rendered" "cd '$MAE' && node scripts/check-maestro-coverage.js"

# Negative controls on a copy of mobile/ (no node_modules needed: the lint is fs-only).
_cov_plant() {
  local c="$T/cov-plant"; rm -rf "$c"; mkdir -p "$c"
  (cd "$MAE" && tar --exclude=node_modules -cf - app components scripts .maestro) | (cd "$c" && tar -xf -) || return 1
  (cd "$c" && "$1") || return 1
  (cd "$c" && node scripts/check-maestro-coverage.js >/dev/null 2>&1)
}
_p_noflow() { rm .maestro/gallery.yaml; }
_p_staleid() { sed -i 's/testID="settings-gallery-row"/testID="settings-components-row"/' 'app/(app)/settings.tsx' && grep -q settings-components-row 'app/(app)/settings.tsx'; }
_p_noroot() { printf 'export default function Promo() { return null; }\n' > app/promo.tsx; }
_p_skip() { printf '// maestro-coverage: skip placeholder route, no UI yet\nexport default function Promo() { return null; }\n' > app/promo.tsx; }
refuses "maestro coverage: a screen with no flow fails" "_cov_plant _p_noflow"
refuses "maestro coverage: a flow targeting a renamed testID fails" "_cov_plant _p_staleid"
refuses "maestro coverage: a route without a -screen/-sheet root testID fails" "_cov_plant _p_noroot"
check "maestro coverage: a route opted out with a reason passes" "_cov_plant _p_skip"

_flows_tagged() {
  python3 - "$MAE/.maestro" <<'PY'
import sys, pathlib, yaml
bad = []
for f in sorted(pathlib.Path(sys.argv[1]).glob("*.yaml")):
    head = next(yaml.safe_load_all(f.read_text()))
    tags = set(head.get("tags") or [])
    if not tags & {"smoke", "demo", "staging"}:
        bad.append(f"{f.name}: no smoke/demo/staging tag")
    if "smoke" in tags and "signin-demo" in f.read_text():
        bad.append(f"{f.name}: a smoke flow signs in through demo mode (absent on EAS builds)")
print("\n".join(bad)); sys.exit(1 if bad else 0)
PY
}
check "every flow is tagged, and no smoke flow depends on demo mode" _flows_tagged
check "EAS e2e workflow runs only the smoke tag" \
  "python3 -c \"import yaml; j=yaml.safe_load(open('$MAE/.eas/workflows/e2e.yml'))['jobs']; ms=[x for x in j.values() if x.get('type')=='maestro']; assert len(ms)==2 and all(x['params']['include_tags']=='smoke' for x in ms)\""

_maestro_syntax() {
  local f out bad=0
  for f in "$MAE"/.maestro/*.yaml "$MAE"/.maestro/common/*.yaml; do
    out=$(JAVA_TOOL_OPTIONS= maestro check-syntax "$f" 2>&1) || { echo "$f: $out"; bad=1; }
  done
  # negative control: a misspelt command must be rejected
  printf 'appId: x\n---\n- tapOnn: foo\n' > "$T/bad-flow.yaml"
  JAVA_TOOL_OPTIONS= maestro check-syntax "$T/bad-flow.yaml" >/dev/null 2>&1 && { echo "check-syntax accepted a bad flow"; bad=1; }
  [ "$bad" = 0 ]
}
# `command -v maestro` is not enough: the launcher is a shell script that fails without a
# Java runtime, and a check that cannot run must read as SKIP, never as FAIL or PASS.
if command -v maestro >/dev/null 2>&1 && JAVA_TOOL_OPTIONS= maestro --version >/dev/null 2>&1; then
  check "maestro check-syntax: every flow parses (and a bad one is rejected)" _maestro_syntax
else
  skip "maestro check-syntax: every flow parses (and a bad one is rejected)" "maestro with a Java runtime"
fi
