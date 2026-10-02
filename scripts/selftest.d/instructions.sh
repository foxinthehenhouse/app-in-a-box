# Instruction quality (teardown, 2026-10-01): sourced by selftest.sh with $KIT, $APP (rendered app,
# cwd), $T and the check/refuses helpers. Pins the teardown fixes to the kit's skills,
# agents, docs and READMEs so none of them quietly regresses. Every check here can
# fail: plant the old text back and the matching line goes red.
ROOT="$KIT/../.."
SK="$KIT/skills"

# Founder-facing text names no upstream app (-w: the word itself, so "forged" in the
# payments recipe is not a hit). Eval cases are owned elsewhere and not read here.
check "no upstream-app references in founder-facing files (README, START_HERE, skills, agents, docs)" \
  "! grep -rniw 'forge' '$ROOT/README.md' '$ROOT/START_HERE.md' '$SK' '$KIT/agents' '$KIT/docs'"

# Phase labels agree with progress.py everywhere a founder reads them.
_phase_labels() {
  ! grep -q 'phase 1a (`validate-idea`)' "$SK/interview/SKILL.md" \
    && ! grep -q 'Interview (1b)' "$SK/validate-idea/SKILL.md" \
    && grep -q '1a. Shape' "$ROOT/START_HERE.md" && grep -q '1b. Idea check' "$ROOT/START_HERE.md" \
    && grep -q '2. Prototype' "$ROOT/START_HERE.md" \
    && ! grep -qE '1 · Interview|2 · Design' "$ROOT/README.md"
}
check "phase labels agree with progress.py (1a Shape, 1b Idea check, 2 Prototype)" _phase_labels

# Every skill and agent that uses $KIT says how to resolve it.
_kit_resolved() {
  local f bad=0
  for f in "$SK"/*/SKILL.md "$KIT"/agents/*.md; do
    if grep -q '\$KIT' "$f" && ! grep -q 'plugin root' "$f"; then echo "uses \$KIT, never resolves it: $f"; bad=1; fi
  done
  [ "$bad" = 0 ]
}
check "every skill and agent that uses \$KIT says how to resolve it" _kit_resolved

check "design-directions is a reference: never marks the design phase done (prototype owns progress.design)" \
  "! grep -q 'progress.design: done' '$SK/design-directions/SKILL.md' && grep -q 'progress.design: done' '$SK/prototype/SKILL.md'"

check "scaffold has a match check against SCREENS.md before the bootstrap commit, and turns hooks on first" \
  "grep -q '^### Match check' '$SK/scaffold/SKILL.md' && grep -q 'design-critic' '$SK/scaffold/SKILL.md' \
   && grep -q 'Turn the hooks on \*\*first\*\*' '$SK/scaffold/SKILL.md'"

check "new-app carries the never-list and is the hook until phase 4" \
  "grep -q 'until phase 4 installs the hooks' '$SK/new-app/SKILL.md' && grep -q 'solve a CAPTCHA' '$SK/new-app/SKILL.md'"

check "harness defers branch protection to phase 7; doctor Full applies it and records progress.verify" \
  "grep -q 'deferred to phase 7' '$SK/harness/SKILL.md' && grep -q '/branches/main/protection' '$SK/doctor/SKILL.md' \
   && grep -q 'progress.verify: done' '$SK/doctor/SKILL.md' && ! grep -q 'GitHub protection + AI review' '$SK/new-app/SKILL.md'"

check "accounts creates .env before a secret is pasted into it" "grep -q 'touch .env' '$SK/accounts/SKILL.md'"

check "provision has the owner fallback for a hook-refused first push, and TROUBLESHOOTING names the symptom" \
  "grep -q 'refused by .bash-safety' '$SK/provision/SKILL.md' && grep -q 'git ls-remote --heads origin main' '$SK/provision/SKILL.md' \
   && grep -q 'pushing to main/master' '$KIT/docs/TROUBLESHOOTING.md'"

check "interview counts its own questions (14) and the schema carries the merge policy key" \
  "grep -q 'about 14 questions' '$SK/interview/SKILL.md' && grep -q 'auto_merge_low_risk: false' '$SK/interview/SKILL.md'"

check "one merge-policy key: AGENTS.md and pr-review both read policy.auto_merge_low_risk" \
  "grep -q 'policy.auto_merge_low_risk' '$APP/AGENTS.md' && grep -q 'policy.auto_merge_low_risk' '$APP/.agents/skills/pr-review/SKILL.md' \
   && grep -q -- '--merge-ok' '$APP/.agents/skills/pr-review/SKILL.md'"

check "pr-review reviews an inline diff as the PR and names the gates it couldn't run" \
  "grep -q 'inline diff' '$APP/.agents/skills/pr-review/SKILL.md' && grep -q 'gates not run' '$APP/.agents/skills/pr-review/SKILL.md'"

# Reviewers: blockers on sight and one parseable output shape; roles name real paths.
_reviewer_shape() {
  local f
  for f in correctness-reviewer design-a11y-reviewer; do
    grep -q '^Verdict: PASS | BLOCKED | ADVISORY' "$APP/.agents/agents/$f.md" \
      && grep -q 'Checked and clean' "$APP/.agents/agents/$f.md" \
      && grep -q 'docs/product/specs/' "$APP/.agents/agents/$f.md" || { echo "$f"; return 1; }
  done
  grep -q '^## Blockers on sight' "$APP/.agents/agents/correctness-reviewer.md" \
    && grep -q 'docs/product/specs/' "$APP/.agents/agents/lead-engineer.md" \
    && grep -q '^Verified:' "$APP/.agents/agents/lead-engineer.md" \
    && ! grep -rq 'components/ui.tsx' "$APP/.agents/agents"
}
check "reviewers have blockers-on-sight, a spec-reading step and an exact output shape; roles name real paths" _reviewer_shape

# TASTE.md travels into the app and is protected like tokens.json.
_taste_travels() {
  local d="$T/taste-app"
  rm -rf "$d" && mkdir -p "$d/docs/design" && echo 'mine' > "$d/docs/design/TASTE.md"
  python3 "$KIT/scripts/render.py" --target "$d" --name T --slug taste-app --bundle-id com.t.taste --owner t --force >/dev/null || return 1
  grep -qx mine "$d/docs/design/TASTE.md" || { echo "overwritten with --force"; return 1; }
  rm "$d/docs/design/TASTE.md"
  python3 "$KIT/scripts/render.py" --target "$d" --name T --slug taste-app --bundle-id com.t.taste --owner t >/dev/null || return 1
  cmp -s "$KIT/docs/TASTE.md" "$d/docs/design/TASTE.md" && [ -f "$APP/docs/design/TASTE.md" ]
}
check "render copies docs/TASTE.md to docs/design/TASTE.md and never overwrites an existing one" _taste_travels

check "generated designers and reviewers read the app's TASTE.md" \
  "grep -q 'docs/design/TASTE.md' '$APP/.agents/agents/ux-designer.md' \
   && grep -q 'docs/design/TASTE.md' '$APP/.agents/agents/design-a11y-reviewer.md' \
   && grep -q 'docs/design/TASTE.md' '$APP/.agents/skills/feature-discovery/SKILL.md' \
   && grep -q 'docs/design/TASTE.md' '$APP/.agents/skills/pr-review/SKILL.md'"

check "copywriter, visual and interaction designers carry good/bad examples" \
  "grep -q 'not \"Submit\"' '$KIT/agents/copywriter.md' && grep -q 'Welcome back' '$KIT/agents/copywriter.md' \
   && grep -q '^- Bad: ' '$KIT/agents/visual-designer.md' && grep -q 'A tweak: ' '$KIT/agents/interaction-designer.md'"

# Every spawned team agent declares tools (render.py derives Codex read-only from it).
_agent_tools() {
  local f bad=0
  for f in "$KIT"/agents/*.md; do
    [ "$(basename "$f")" = product-advisor.md ] && continue
    grep -q '^tools: ' "$f" || { echo "no tools: $f"; bad=1; }
  done
  [ "$bad" = 0 ] && grep -qx 'tools: Read, Write' "$KIT/agents/scribe.md" \
    && grep -q '^tools: .*WebSearch' "$KIT/agents/market-analyst.md" \
    && ! grep -q 'PUL-' "$KIT/agents/flow-architect.md" \
    && grep -qx 'model: sonnet' "$KIT/agents/copywriter.md"
}
check "every spawned team agent declares tools; critic and advisors read-only; copy on Sonnet (owner call); no ticket ids in agent prose" _agent_tools

check "new-worktree deletes merged branches with -d, never -D" \
  "grep -q 'git branch -d <branch>' '$APP/.agents/skills/new-worktree/SKILL.md' && ! grep -q 'branch -D ' '$APP/.agents/skills/new-worktree/SKILL.md'"

check "db-migrations rule shows the initplan-safe policy form in its example" \
  "grep -q '(select auth.uid()) = user_id' '$APP/.agents/rules/db-migrations.md'"

check "first-feature skips the PostHog ticket when analytics is declined" \
  "grep -q 'stack.analytics: none' '$SK/first-feature/SKILL.md'"

check "build-feature writes the Maestro flow even without maestro and says it is unrun" \
  "grep -q 'written but unrun' '$APP/.agents/skills/build-feature/SKILL.md'"

check "feature-discovery names its three subagents" \
  "grep -q 'product-manager' '$APP/.agents/skills/feature-discovery/SKILL.md' && grep -q 'ux-designer' '$APP/.agents/skills/feature-discovery/SKILL.md' \
   && grep -q 'lead-engineer' '$APP/.agents/skills/feature-discovery/SKILL.md'"

# Version identities: README states the manifest version, and only that one.
_versions_agree() {
  local v; v=$(python3 -c "import json;print(json.load(open('$KIT/.claude-plugin/plugin.json'))['version'])")
  grep -q "Alpha (v$v)" "$ROOT/README.md" && grep -q "alpha%20v$v-" "$ROOT/README.md" && ! grep -q 'Alpha (v0.1)' "$ROOT/README.md"
}
check "README states the plugin manifest version, once and consistently" _versions_agree

check "START_HERE install commands name the real marketplace, not a placeholder" \
  "grep -q 'foxinthehenhouse/app-in-a-box' '$ROOT/START_HERE.md' && ! grep -q '<owner>/app-in-a-box' '$ROOT/START_HERE.md'"

check "kit and README agree on the generated skill count (14, including land)" \
  "grep -q '14 skills' '$SK/harness/SKILL.md' && grep -q '14 skills' '$ROOT/README.md' \
   && [ \$(ls -d '$APP'/.agents/skills/*/ | wc -l) -eq 14 ]"
