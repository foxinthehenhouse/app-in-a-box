# Shape-first team and canon (PUL-542): sourced by selftest.sh with $KIT, $APP, $T and
# check/refuses. Pins the named agents, the taste and cost canon, and the shape and
# prototype skills' key promises, so none of them can quietly disappear.

# Every team member: frontmatter name = file, a description, a routed model and effort,
# and an identity ("You are **Name**") at the top of the body.
_team_identities() {
  python3 - "$KIT/agents" <<'PY'
import pathlib, re, sys
agents = sorted(pathlib.Path(sys.argv[1]).glob("*.md"))
assert len(agents) >= 9, f"expected the 9-person team, found {len(agents)}"
for f in agents:
    text = f.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{f.name}: no frontmatter"
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)
    assert meta.get("name") == f.stem, f"{f.name}: name != file"
    assert len(meta.get("description", "")) > 40, f"{f.name}: thin description"
    assert meta.get("model") in {"haiku", "sonnet", "opus", "fable"}, f"{f.name}: model"
    assert meta.get("effort") in {"low", "medium", "high"}, f"{f.name}: effort"
    assert re.search(r"^You are \*\*[A-Z][a-z]+\*\*", m.group(2).lstrip(), re.M), f"{f.name}: no identity"
PY
}
check "every team agent has an identity, a routed model and effort" "_team_identities"

_team_contracts() {
  local a="$KIT/agents"
  grep -q 'design/brief.json' "$a/product-advisor.md" && grep -q 'product-judgement.md' "$a/product-advisor.md" || return 1
  for f in flow-architect visual-designer interaction-designer design-critic; do
    grep -q 'docs/TASTE.md' "$a/$f.md" && grep -q 'brief.json\|prototype' "$a/$f.md" || { echo "$f"; return 1; }
  done
  grep -q 'prototype.py" check' "$a/design-critic.md" && grep -q 'Read the artifact first' "$a/design-critic.md" || return 1
  grep -q 'never invent' "$a/scribe.md" && grep -qx 'model: haiku' "$a/scribe.md" && grep -qx 'model: opus' "$a/product-advisor.md"
}
check "team contracts: advisor asks, designers follow TASTE.md, critic lints first, scribe is cheap" "_team_contracts"

_canon() {
  local t="$KIT/docs/TASTE.md" c="$KIT/docs/COST.md"
  for h in "## Product" "## Visual" "## Copy" "## Three diagnostics (run them on every key screen)" "## Anti-slop list (fail on sight)"; do
    grep -qxF "$h" "$t" || { echo "TASTE lost: $h"; return 1; }
  done
  grep -q 'Specs, not markup' "$c" && grep -q '^## The brief' "$c" || return 1
  # The brief schema in COST.md is the one scribe writes and every helper reads.
  for k in '"app"' '"users"' '"core_loop"' '"v1_features"' '"maybe_features"' '"feel"' '"validation"' '"open_questions"'; do
    grep -q "$k" "$c" || { echo "brief lost $k"; return 1; }
  done
}
check "TASTE.md and COST.md keep their sections and the brief schema" "_canon"

_skills_promises() {
  local s="$KIT/skills/shape/SKILL.md" p="$KIT/skills/prototype/SKILL.md"
  grep -q 'at most 1–2 per round' "$s" && grep -q '2–3 per round' "$s" && grep -q 'market-analyst' "$s" \
    && grep -q 'design/brief.json' "$s" && grep -q 'progress.interview: done' "$s" || { echo shape; return 1; }
  grep -q 'prototype.py" check' "$p" && grep -q 'prototype.py" render' "$p" && grep -q 'prototype.py" freeze' "$p" \
    && grep -q 'only if its MCP is connected' "$p" && grep -q 'design-critic' "$p" \
    && grep -q 'Never hand-write the prototype HTML' "$p" || { echo prototype; return 1; }
  grep -q 'docs/product/SCREENS.md' "$KIT/skills/scaffold/SKILL.md"
}
check "shape asks few questions and starts the idea check; prototype lints, gates, freezes; scaffold builds from SCREENS.md" "_skills_promises"
