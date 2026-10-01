# PUL-550 land loop: sourced by selftest.sh with $KIT, $APP, $T and check/refuses.
# Drives the generated repo's real land.py through a fake `gh` on PATH, one fixture per
# PR state, and asserts the ONE next action for each, including the priority order.
LAND="$APP/.agents/skills/land/land.py"
FAKE="$T/fake-gh"; mkdir -p "$FAKE/bin"
cat > "$FAKE/bin/gh" <<'GH'
#!/usr/bin/env bash
# Fake gh: answers the three calls land.py makes from fixture files in $FAKE_GH_DIR.
[ -e "$FAKE_GH_DIR/fail" ] && exit 1
case "$1 $2" in
  "pr view") cat "$FAKE_GH_DIR/pr.json" ;;
  "repo view") echo '{"owner":{"login":"acme"},"name":"app"}' ;;
  "api graphql") cat "$FAKE_GH_DIR/threads.json" ;;
  *) exit 1 ;;
esac
GH
chmod +x "$FAKE/bin/gh"

cat > "$T/land_case.py" <<'PY'
import json, sys
# land_case.py <dir> <scenario>: write pr.json + threads.json for one PR state.
d, name = sys.argv[1], sys.argv[2]
HEAD = "a" * 40
ok = {"__typename": "CheckRun", "name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}
pr = {"number": 7, "url": "u", "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE",
      "headRefOid": HEAD, "headRefName": "feat/x", "baseRefName": "main", "reviewDecision": "",
      "statusCheckRollup": [ok], "comments": []}
verdict = lambda sha, r: {"body": f"Verdict: ...\n<!-- appbox-verdict sha={sha} result={r} -->"}
threads = []
if name == "conflict":
    pr["mergeable"] = "CONFLICTING"
if name == "conflict+red":
    pr["mergeable"] = "CONFLICTING"
    pr["statusCheckRollup"] = [dict(ok, conclusion="FAILURE", name="tests")]
if name == "red":
    pr["statusCheckRollup"] = [dict(ok, conclusion="FAILURE", name="tests", detailsUrl="x")]
if name == "status-red":
    pr["statusCheckRollup"] = [{"__typename": "StatusContext", "context": "deploy", "state": "ERROR"}]
if name == "thread":
    threads = [{"isResolved": False, "isOutdated": False, "path": "a.py", "line": 3,
                "comments": {"nodes": [{"author": {"login": "bot"}, "url": "t"}]}}]
if name == "resolved-thread":
    threads = [{"isResolved": True, "path": "a.py", "comments": {"nodes": []}}]
if name == "pending":
    pr["statusCheckRollup"] = [dict(ok, status="IN_PROGRESS", conclusion=None)]
if name == "stale":
    pr["comments"] = [verdict("b" * 40, "safe")]
if name == "not-ready":
    pr["comments"] = [verdict(HEAD, "not-ready")]
if name in ("safe", "safe-short", "draft", "changes", "owner"):
    sha = HEAD[:12] if name == "safe-short" else HEAD
    pr["comments"] = [verdict(sha, "owner" if name == "owner" else "safe")]
if name == "draft":
    pr["isDraft"] = True
if name == "changes":
    pr["reviewDecision"] = "CHANGES_REQUESTED"
if name == "merged":
    pr["state"] = "MERGED"
json.dump(pr, open(f"{d}/pr.json", "w"))
json.dump({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": threads}}}}},
          open(f"{d}/threads.json", "w"))
PY

# _land <scenario> <expected action> [land.py args...]
_land() {
  local d="$T/land-$1" got
  rm -rf "$d"; mkdir -p "$d"
  python3 "$T/land_case.py" "$d" "$1" || return 1
  got=$(cd "$APP" && PATH="$FAKE/bin:$PATH" FAKE_GH_DIR="$d" python3 "$LAND" "${@:3}" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['action'])") || return 1
  [ "$got" = "$2" ] || { echo "$1: expected $2, got $got"; return 1; }
}
_land_all() {
  _land conflict resolve_conflict && _land conflict+red resolve_conflict \
    && _land red fix_ci && _land status-red fix_ci && _land thread address_threads \
    && _land resolved-thread review && _land pending wait_ci && _land green review \
    && _land stale review && _land not-ready fix_findings && _land draft mark_ready \
    && _land changes ask_owner && _land owner ask_owner && _land safe ask_owner \
    && _land safe merge --merge-ok && _land safe-short merge --merge-ok && _land merged done
}
check "land: one next action per PR state, in order (conflict > CI > threads > wait > review > merge)" "_land_all"

_land_blocked() {
  local d="$T/land-fail"
  mkdir -p "$d"; : > "$d/fail"
  (cd "$APP" && PATH="$FAKE/bin:$PATH" FAKE_GH_DIR="$d" python3 "$LAND") | grep -q '"action": "blocked"'
}
check "land: no gh access is 'blocked' with a reason, never a guess" "_land_blocked"

# pr-review's marker must be one land.py parses, and the loop keeps its never-rules: no
# hook skipping, no force-push, no empty commit to kick CI (patterns spelled as regex
# classes so this file never contains the forbidden flags literally).
_land_contract() {
  local s="$APP/.agents/skills"
  grep -q 'appbox-verdict sha=<full head sha you reviewed> result=safe|owner|not-ready' "$s/pr-review/SKILL.md" \
    && grep -q 'appbox-verdict' "$LAND" \
    && ! grep -nE -- '[-][-]no[-]verify|push +(-f|[-][-]force)|[-][-]force[-]with[-]lease|[-][-]allow[-]empty' "$s/land/SKILL.md" \
    && grep -q '`land` skill' "$s/build-feature/SKILL.md" && grep -q '`land` skill' "$APP/AGENTS.md"
}
check "land: pr-review stamps the head it reviewed; no hook-skip, force-push or empty commit in the loop" "_land_contract"

# Found while building land: a tool cache left in the template (ruff/pytest/npm) crashed
# the render on a binary file. Plant one, render, and prove it's skipped, not copied.
_render_skips_caches() {
  local c="$KIT/template/.ruff_cache" out="$T/render-cache"
  mkdir -p "$c/0.1" && printf '\375\376binary' > "$c/0.1/blob" && printf '\375' > "$c/.weird"
  python3 "$KIT/scripts/render.py" --target "$out" --name "Penny Jar" --slug penny-jar \
    --bundle-id com.example.pennyjar --owner example >/dev/null 2>&1; local rc=$?
  rm -rf "$c"
  [ "$rc" = 0 ] && [ ! -e "$out/.ruff_cache" ] && [ -f "$out/AGENTS.md" ]
}
check "render skips tool caches left in the template (no crash on a binary cache file)" "_render_skips_caches"
