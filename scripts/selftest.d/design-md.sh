# DESIGN.md: generated from design/tokens.json, kept honest by a drift gate. Sourced by
# selftest.sh with $KIT, $APP, $T and the check/skip helpers. One implementation
# (template/scripts/design_md.py, re-exported by the kit's scripts/design_md.py) is
# proven here to: be written by freeze and by render, keep Stitch's frontmatter schema,
# keep hand prose across regeneration, and FAIL --check on a hand edit or a token change.
DM_PY="$KIT/template/scripts/design_md.py"
DM_PROTO="$KIT/scripts/prototype.py"
DM_FIX="$KIT/../../scripts/fixtures/prototype.json"
DMF="$T/dm-frozen"

printf '%s' '{"direction": "athletic", "mode": "dark", "variants": {"home": "cards"}}' > "$T/dm-choices.json"
rm -rf "$DMF"
check "design.md: freeze writes DESIGN.md beside tokens.json, SCREENS.md and choices.json" \
  "python3 '$DM_PROTO' freeze '$DM_FIX' '$T/dm-choices.json' --target '$DMF' | grep -q 'wrote $DMF/DESIGN.md' \
   && [ -f '$DMF/design/tokens.json' ] && [ -f '$DMF/docs/product/SCREENS.md' ] && [ -f '$DMF/design/choices.json' ] \
   && cd '$DMF' && python3 '$DM_PY' --check"

_dm_frontmatter() {  # YAML that parses, Stitch's top-level keys only, home palette projected
  python3 - "$1/DESIGN.md" "$1/design/tokens.json" <<'PYEOF'
import json, sys, yaml
text, tok = open(sys.argv[1]).read(), json.load(open(sys.argv[2]))
assert text.startswith("---\n"), "no frontmatter"
fm = yaml.safe_load(text.split("---\n")[1])
allowed = {"version", "name", "description", "omitted", "colors", "typography", "rounded", "spacing", "components"}
assert set(fm) <= allowed, set(fm) - allowed
assert fm["version"] == "alpha" and fm["name"] == tok["name"]
pal = tok["color"][tok["mode"]]
assert fm["colors"]["primary"] == pal["accent"] and fm["colors"]["background"] == pal["bg"], fm["colors"]
assert fm["typography"]["body"]["fontSize"] == f"{tok['type']['body']['size']}px", fm["typography"]
assert fm["rounded"]["md"] == f"{tok['radius']['md']}px" and fm["components"]["button-primary"]["backgroundColor"] == "{colors.primary}"
PYEOF
}
check "design.md: frontmatter is YAML with only Stitch's top-level keys, from the home palette" "_dm_frontmatter '$DMF'"
check "design.md: Stitch's eight sections in order, then the extras, then Decisions" \
  "[ \"\$(grep '^## ' '$DMF/DESIGN.md' | tr '\n' '|')\" = \"## Overview|## Colors|## Typography|## Layout|## Elevation & Depth|## Shapes|## Components|## Do's and Don'ts|## Dark Mode|## Motion|## Atmosphere|## Iconography|## Agent Prompt Guide|## Decisions|\" ]"
check "design.md: the frozen atmosphere and the other mode's palette are in the body" \
  "grep -q '^The light behind each screen, as chosen in the prototype: mode \*\*glow\*\*' '$DMF/DESIGN.md' \
   && grep -q '^| Token | light | dark |$' '$DMF/DESIGN.md'"

_dm_keeps_prose() {  # plant prose + a Decisions entry, re-freeze another direction: both survive
  local d="$T/dm-prose"; rm -rf "$d"; cp -r "$DMF" "$d" || return 1
  python3 - "$d/DESIGN.md" <<'PYEOF' || return 1
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace("## Colors\n", "Quiet and sure-footed: planted prose paragraph.\n\n## Colors\n", 1)
open(p, "w").write(s + "- 2026-10-01: planted decision, kept on purpose.\n")
PYEOF
  printf '%s' '{"direction": "calm", "mode": "light"}' > "$T/dm-choices2.json"
  python3 "$DM_PROTO" freeze "$DM_FIX" "$T/dm-choices2.json" --target "$d" >/dev/null || return 1
  grep -q '^Quiet and sure-footed: planted prose paragraph.$' "$d/DESIGN.md" \
    && grep -q '^- 2026-10-01: planted decision, kept on purpose.$' "$d/DESIGN.md" \
    && grep -q '^name: "calm"$' "$d/DESIGN.md" && [ "$(grep -c '^## Colors$' "$d/DESIGN.md")" -eq 1 ] \
    && (cd "$d" && python3 "$DM_PY" --check >/dev/null)
}
check "design.md: re-freezing keeps a planted prose paragraph and the Decisions log" "_dm_keeps_prose"

_dm_refuses() {  # <python edit of s (DESIGN.md text) or t (tokens dict)> <expected message>
  local d="$T/dm-neg"; rm -rf "$d"; cp -r "$DMF" "$d" || return 1
  python3 - "$d" "$1" <<'PYEOF' || return 1
import json, sys
d, edit = sys.argv[1], sys.argv[2]
s = open(f"{d}/DESIGN.md").read(); t = json.load(open(f"{d}/design/tokens.json"))
exec(edit)
open(f"{d}/DESIGN.md", "w").write(s); json.dump(t, open(f"{d}/design/tokens.json", "w"), indent=2)
PYEOF
  local out rc
  out=$(cd "$d" && python3 "$DM_PY" --check); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -qF -- "$2" && printf '%s\n' "$out" | grep -q '^DESIGN.md check FAILED'
}
check "design.md --check catches: a hand edit inside a generated block" \
  "_dm_refuses \"s = s.replace('| Primary text |', '| Body copy |')\" \"DESIGN.md: generated block 'colors' differs from design/tokens.json\""
check "design.md --check catches: a hand edit to the frontmatter" \
  "_dm_refuses \"s = s.replace('version: \\\"alpha\\\"', 'version: \\\"beta\\\"')\" 'DESIGN.md: frontmatter differs from design/tokens.json'"
check "design.md --check catches: a token changed without regenerating" \
  "_dm_refuses \"t['radius']['md'] += 2\" \"DESIGN.md: generated block 'shapes' differs from design/tokens.json\""
check "design.md --check catches: a deleted generated block" \
  "_dm_refuses \"import re; s = re.sub(r'<!-- design.md:generated:motion -->.*?<!-- /design.md:generated:motion -->', '', s, flags=re.S)\" \"DESIGN.md: generated block 'motion' is missing\""
check "design.md --check allows: prose added outside the markers" \
  "d='$T/dm-ok'; rm -rf \"\$d\"; cp -r '$DMF' \"\$d\" && printf '\nMore words of our own.\n' >> \"\$d/DESIGN.md\" && cd \"\$d\" && python3 '$DM_PY' --check"
check "design.md --check refuses: no DESIGN.md at all" \
  "d='$T/dm-none'; rm -rf \"\$d\"; mkdir -p \"\$d/design\" && cp '$DMF/design/tokens.json' \"\$d/design/\" && cd \"\$d\" && ! out=\$(python3 '$DM_PY' --check) && printf '%s' \"\$out\" | grep -q 'DESIGN.md: missing'"

# The generated app: render ships one, the kit and the app run one implementation, and
# the app's CI, pre-commit, agent docs and guard-wiring test all know about it.
check "design.md: render ships DESIGN.md in the app, and it passes the app's own --check" \
  "[ -f '$APP/DESIGN.md' ] && cd '$APP' && python3 scripts/design_md.py --check"
check "design.md: the app's copy is the kit's (one implementation, a shim in the kit)" \
  "cmp -s '$DM_PY' '$APP/scripts/design_md.py' && grep -q 'template/scripts/design_md.py' '$KIT/scripts/design_md.py' \
   && python3 '$KIT/scripts/design_md.py' --tokens '$APP/design/tokens.json' --out '$APP/DESIGN.md' --check >/dev/null"
_dm_render_keeps_prose() {
  local d="$T/dm-app"; rm -rf "$d"; mkdir -p "$d"
  local r=(python3 "$KIT/scripts/render.py" --target "$d" --name "Penny Jar" --slug penny-jar --bundle-id com.alex.pennyjar --owner alex --one-liner "x")
  "${r[@]}" >/dev/null || return 1
  printf '\nOur own paragraph about the feel.\n' >> "$d/DESIGN.md"
  python3 -c "import json;p='$d/design/tokens.json';t=json.load(open(p));t['radius']['lg']=24;json.dump(t,open(p,'w'),indent=2)" || return 1
  "${r[@]}" --force >/dev/null || return 1
  grep -q '^Our own paragraph about the feel.$' "$d/DESIGN.md" && grep -q '^| `radius.lg` | 24px |' "$d/DESIGN.md" \
    && (cd "$d" && python3 scripts/design_md.py --check >/dev/null)
}
check "design.md: re-render --force refreshes the generated blocks and never overwrites hand prose" "_dm_render_keeps_prose"
check "design.md: the app's CI and pre-commit run --check, and test_guards_wired sees both" \
  "grep -q 'run: python3 scripts/design_md.py --check' '$APP/.github/workflows/ci.yml' \
   && grep -q 'python3 scripts/design_md.py --check' '$APP/.githooks/pre-commit' \
   && grep -q 'glob(\"design_md.py\")' '$APP/tests/harness/test_guards_wired.py' \
   && grep -q 'def test_design_md_check_runs_in_ci_and_pre_commit' '$APP/tests/harness/test_guards_wired.py'"
_dm_wiring_plant() {  # the app's own wiring test must FAIL when CI stops running --check
  local d="$T/dm-wired"; rm -rf "$d"; mkdir -p "$d"
  (cd "$APP" && tar --exclude=node_modules --exclude=.git --exclude=.venv -cf - .github .githooks scripts tests pyproject.toml) | (cd "$d" && tar -xf -) || return 1
  sed -i.bak 's#python3 scripts/design_md.py --check#python3 scripts/design_md.py#' "$d/.github/workflows/ci.yml" && rm -f "$d/.github/workflows/ci.yml.bak"
  local out; out=$(cd "$d" && "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider tests/harness/test_guards_wired.py -k design_md_check_runs 2>&1) && return 1
  printf '%s' "$out" | grep -q "is not run by: \['ci.yml'\]"
}
if [ -x "$APP/.venv/bin/python" ]; then
  check "design.md: test_guards_wired fails when CI regenerates instead of checking (negative control)" "_dm_wiring_plant"
else
  skip "design.md: test_guards_wired negative control" "the app's venv"
fi
_dm_precommit() {  # the app's pre-commit refuses a staged token change with a stale DESIGN.md
  local d="$T/dm-hook"; rm -rf "$d"; cp -r "$DMF" "$d" || return 1
  mkdir -p "$d/scripts" "$d/.githooks" && cp "$APP/scripts/design_md.py" "$d/scripts/" && cp "$APP/.githooks/pre-commit" "$d/.githooks/" || return 1
  cd "$d" && git init -q -b feat/x && git add -A || return 1
  local G="git -c user.email=t@example.com -c user.name=selftest -c core.hooksPath=.githooks"
  $G commit -qm base >/dev/null 2>&1 || return 1
  python3 -c "import json;p='design/tokens.json';t=json.load(open(p));t['radius']['md']+=2;json.dump(t,open(p,'w'),indent=2)" && git add design/tokens.json
  local out; out=$($G commit -qm stale 2>&1) && { cd "$APP"; return 1; }
  printf '%s' "$out" | grep -q 'pre-commit: DESIGN.md has drifted from design/tokens.json' || { cd "$APP"; return 1; }
  python3 scripts/design_md.py >/dev/null && git add DESIGN.md && $G commit -qm fresh >/dev/null 2>&1; local rc=$?
  cd "$APP"; return $rc
}
check "design.md: the app's pre-commit refuses a stale DESIGN.md, then takes the regenerated one" "_dm_precommit"
check "design.md: AGENTS.md and mobile/AGENTS.md say read DESIGN.md first, change tokens via the design flow" \
  "grep -q 'Read \`DESIGN.md\` before any UI work' '$APP/AGENTS.md' && grep -q 'change tokens via the design flow' '$APP/AGENTS.md' \
   && grep -q 'Read \`../DESIGN.md\` before any UI work' '$APP/mobile/AGENTS.md' && grep -q 'Change tokens through the' '$APP/mobile/AGENTS.md' \
   && grep -q '@AGENTS.md' '$APP/CLAUDE.md'"
check "design.md: Stitch's format is credited (Apache-2.0) with its licence text" \
  "grep -q '^## DESIGN.md format (Google Stitch)' '$KIT/../../THIRD_PARTY_NOTICES.md' \
   && grep -q 'licenses/Apache-2.0-design-md.txt' '$KIT/../../THIRD_PARTY_NOTICES.md' \
   && grep -q 'Apache License' '$KIT/../../licenses/Apache-2.0-design-md.txt'"
cd "$APP"
