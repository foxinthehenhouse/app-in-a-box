# Discoverability: sourced by selftest.sh with $KIT, $APP, $T and the check/refuses
# helpers. The kit describes itself one way everywhere (manifests, README hero,
# llms.txt, the maintainer settings), the keywords are identical in both plugin
# manifests, the version agrees with CHANGELOG.md, and every doc link resolves. Each
# rule is proven to FAIL on a planted drift in a copy of the repo, never the real one.
DISC_ROOT="$KIT/../.."
DISC_PY="$DISC_ROOT/scripts/check_discoverability.py"

check "discoverability: manifests, README, llms.txt, guides and CHANGELOG agree and link" \
  "python3 '$DISC_PY' --root '$DISC_ROOT'"

# A fresh copy of the repo's files (tracked + new, not ignored), so a plant never
# touches the worktree and one plant can't leak into the next.
_disc_copy() {
  local c="$T/disc"; rm -rf "$c"; mkdir -p "$c"
  (cd "$DISC_ROOT" && git ls-files -co --exclude-standard -z | xargs -0 tar -cf - 2>/dev/null) | (cd "$c" && tar -xf -)
  [ -f "$c/llms.txt" ] && [ -f "$c/.claude-plugin/marketplace.json" ]
}
_disc_refuses() {  # <python edit, run in the copy's root> <expected message>
  local out rc
  _disc_copy || return 1
  (cd "$T/disc" && python3 -c "import json, pathlib, re
def J(p): return json.loads(pathlib.Path(p).read_text())
def W(p, d): pathlib.Path(p).write_text(json.dumps(d, indent=2))
def T(p): return pathlib.Path(p).read_text()
def S(p, s): pathlib.Path(p).write_text(s)
$1") || return 1
  out=$(python3 "$T/disc/scripts/check_discoverability.py" --root "$T/disc"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -qF -- "$2"
}
CP=plugins/app-in-a-box/.claude-plugin/plugin.json
XP=plugins/app-in-a-box/.codex-plugin/plugin.json
check "discoverability catches: the Codex manifest describing the kit differently" \
  "_disc_refuses \"d=J('$XP'); d['description']='Turn an idea into an app.'; W('$XP', d)\" \
   'positioning: .codex-plugin/plugin.json description differs from the canonical description'"
check "discoverability catches: a marketplace entry with its own description" \
  "_disc_refuses \"d=J('.claude-plugin/marketplace.json'); d['plugins'][0]['description']+=' Fast.'; W('.claude-plugin/marketplace.json', d)\" \
   'positioning: marketplace.json plugins[app-in-a-box].description differs'"
check "discoverability catches: a Codex long description that doesn't open with the canonical one" \
  "_disc_refuses \"d=J('$XP'); d['interface']['longDescription']='Build apps. '+d['interface']['longDescription']; W('$XP', d)\" \
   \"longDescription doesn't start with the canonical description\""
check "discoverability catches: a one-liner over 90 characters" \
  "_disc_refuses \"d=J('.claude-plugin/marketplace.json'); d['metadata']['description']+=' and much, much more besides'; W('.claude-plugin/marketplace.json', d)\" \
   'positioning: the one-liner is'"
check "discoverability catches: a README hero that drifted from the manifests" \
  "_disc_refuses \"S('README.md', T('README.md').replace('A free, open-source plugin', 'A free plugin', 1))\" \
   'positioning: the README hero'"
check "discoverability catches: keywords that differ between the two plugin manifests" \
  "_disc_refuses \"d=J('$XP'); d['keywords']=d['keywords'][:-1]; W('$XP', d)\" \
   'keywords: the Claude and Codex plugin manifests list different keywords'"
check "discoverability catches: a keyword GitHub won't take as a topic" \
  "_disc_refuses \"[W(p, {**J(p), 'keywords': J(p)['keywords']+['React Native']}) for p in ('$CP', '$XP')]\" \
   \"keywords: 'React Native' isn't a valid GitHub topic\""
check "discoverability catches: maintainer topics that drifted from the keywords" \
  "_disc_refuses \"S('docs/MAINTAINERS.md', T('docs/MAINTAINERS.md').replace('app-builder mobile', 'app-builder mobile boilerplate', 1))\" \
   \"keywords: docs/MAINTAINERS.md's topics block differs\""
check "discoverability catches: a version bump with no CHANGELOG entry" \
  "_disc_refuses \"[W(p, {**J(p), 'version': '9.9.9'}) for p in ('$CP', '$XP')]\" \
   \"version: CHANGELOG.md's newest release isn't the manifest version 9.9.9\""
check "discoverability catches: a broken relative link in llms.txt" \
  "_disc_refuses \"S('llms.txt', T('llms.txt') + '- [Gone](docs/guides/no-such-page.md): moved\n')\" \
   'llms.txt: broken link docs/guides/no-such-page.md (no such file)'"
check "discoverability catches: an llms.txt entry that isn't a markdown link" \
  "_disc_refuses \"S('llms.txt', T('llms.txt') + '- docs/guides/what-you-get.md\n')\" \
   \"llms.txt: not a '- [name](url): note' entry\""
check "discoverability catches: a guide linking a heading that doesn't exist" \
  "_disc_refuses \"S('docs/guides/what-you-get.md', T('docs/guides/what-you-get.md') + '\nSee [setup](../../README.md#no-such-heading).\n')\" \
   'what-you-get.md: broken link ../../README.md#no-such-heading (no heading #no-such-heading)'"
check "discoverability catches: a guide with no way back to the Quickstart" \
  "_disc_refuses \"S('docs/guides/what-you-get.md', T('docs/guides/what-you-get.md').replace('README.md#quickstart', 'README.md'))\" \
   \"guides: what-you-get.md doesn't link to the Quickstart\""
check "discoverability catches: a README with no showcase link" \
  "_disc_refuses \"S('README.md', T('README.md').replace('SHOWCASE.md', 'SHOW.md'))\" \
   \"docs: the README doesn't link SHOWCASE.md\""
check "discoverability: the show-your-app issue form parses and asks for a name and a one-liner" \
  "python3 -c \"import yaml; d=yaml.safe_load(open('$DISC_ROOT/.github/ISSUE_TEMPLATE/show-your-app.yml')); ids=[b.get('id') for b in d['body']]; assert d['name'] and 'name' in ids and 'one_liner' in ids, ids\""

# The generated app's README: a small, removable badge, links that resolve in a render,
# and protected so a --force re-render never puts back a badge the owner deleted.
check "generated README: carries the removable 'Built with App in a Box' badge and says how to remove it" \
  "grep -q 'Built with App in a Box' '$APP/README.md' && grep -q 'to remove the badge, delete the next line' '$APP/README.md' \
   && grep -q 'github.com/foxinthehenhouse/app-in-a-box' '$APP/README.md'"
check "generated README: every relative link resolves in a rendered app" \
  "python3 '$DISC_PY' --links '$APP/README.md'"
_disc_readme_broken() {  # a planted copy beside the real one, so its other links resolve
  local f="$APP/disc-readme.md" out rc
  cp "$APP/README.md" "$f" && printf '\n[gone](docs/no-such.md)\n' >> "$f"
  out=$(python3 "$DISC_PY" --links "$f"); rc=$?; rm -f "$f"
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -qxF 'disc-readme.md: broken link docs/no-such.md (no such file)'
}
check "generated README: the link check fails on a planted broken link (negative control)" "_disc_readme_broken"
_disc_readme_protected() {
  local a="$T/disc-app"; rm -rf "$a"
  python3 "$KIT/scripts/render.py" --target "$a" --name "Penny Jar" --slug penny-jar --bundle-id com.alex.pennyjar \
    --owner alex --one-liner "Savers build a daily streak" >/dev/null || return 1
  grep -q 'Built with App in a Box' "$a/README.md" || return 1
  printf '# Penny Jar\n\nMy own words, no badge.\n' > "$a/README.md"
  python3 "$KIT/scripts/render.py" --target "$a" --name "Penny Jar" --slug penny-jar --bundle-id com.alex.pennyjar \
    --owner alex --one-liner "Savers build a daily streak" --force >/dev/null || return 1
  grep -q 'My own words, no badge.' "$a/README.md" && ! grep -q 'Built with App in a Box' "$a/README.md"
}
check "generated README: a --force re-render keeps the owner's README (badge stays deleted)" "_disc_readme_protected"
refuses "generated README: without the protection, a --force re-render would overwrite it (negative control)" \
  "python3 -c \"import sys; sys.path.insert(0, '$KIT/scripts'); import render; render.PROTECTED.discard('README.md'); sys.argv=['render.py','--target','$T/disc-app','--name','Penny Jar','--slug','penny-jar','--bundle-id','com.alex.pennyjar','--owner','alex','--one-liner','x','--force']; render.main(sys.argv[1:])\" >/dev/null; grep -q 'My own words, no badge.' '$T/disc-app/README.md'"
