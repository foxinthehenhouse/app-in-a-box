#!/usr/bin/env bash
# Roll back the latest OTA update on a branch (default: production).
#
#   scripts/rollback-ota.sh                    # PLAN: show what would be rolled back
#   scripts/rollback-ota.sh --yes -m "reason"  # do it
#
# Options: --branch <name> (production) · --runtime <version> (default: the runtime
# of the newest update on the branch) · --platform all|ios|android (all) · -m <msg>
#
# eas-cli has no dry-run, so the default is a plan: it finds the group and prints the
# exact command. With --yes it runs `eas update:rollback <group> --non-interactive`,
# which republishes the update before that group on the same runtime, or rolls back
# to the build's embedded bundle if there is none. Users get it on their next launch
# or two. Run it as a logged-in owner (`eas login`); see docs/runbooks/rollback.md.
#
# EAS=<command> overrides the CLI (default: `eas`, else `npx --yes eas-cli`).
set -euo pipefail

branch=production platform=all runtime="" message="" yes=0
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) branch="$2"; shift 2 ;;
    --platform) platform="$2"; shift 2 ;;
    --runtime) runtime="$2"; shift 2 ;;
    -m|--message) message="$2"; shift 2 ;;
    --yes) yes=1; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done
case "$platform" in all|ios|android) ;; *) echo "--platform must be all, ios or android" >&2; exit 2 ;; esac

if [ -n "${EAS:-}" ]; then read -r -a eas <<<"$EAS"
elif command -v eas >/dev/null 2>&1; then eas=(eas)
else eas=(npx --yes eas-cli); fi

cd "$(dirname "$0")/../mobile"

list=$("${eas[@]}" update:list --branch "$branch" --json --non-interactive --limit 25) || {
  echo "could not list updates on branch '$branch' (logged in? \`eas whoami\`)" >&2; exit 1; }

# The list is newest first; the first group on a runtime is that runtime's latest,
# which is the only group update:rollback accepts.
pick=$(printf '%s' "$list" | python3 -c '
import json, sys
want = sys.argv[1]
groups = json.load(sys.stdin).get("currentPage") or []
if not want and groups:
    want = groups[0]["runtimeVersion"]
for g in groups:
    if g["runtimeVersion"] == want:
        print("\x1f".join([g["group"], g["runtimeVersion"], g.get("platforms", ""),
                         str(g.get("isRollBackToEmbedded", False)),
                         (g.get("message") or "").replace("\x1f", " ").replace("\n", " ")]))
        break
' "$runtime")
if [ -z "$pick" ]; then
  echo "no update on branch '$branch'${runtime:+ for runtime $runtime}: nothing to roll back" >&2; exit 1
fi
IFS=$'\x1f' read -r group rt platforms embedded msg <<<"$pick"
if [ "$embedded" = True ]; then
  echo "the latest update on '$branch' (runtime $rt) is already a rollback to the embedded bundle" >&2; exit 1
fi

cmd=("${eas[@]}" update:rollback "$group" --non-interactive --platform "$platform" --message "${message:-rollback of $group}")
echo "Branch:   $branch"
echo "Runtime:  $rt"
echo "Latest:   $group ($platforms) \"$msg\""
echo "Effect:   republish the update before it on runtime $rt, or the embedded bundle if none"
if [ "$yes" != 1 ]; then
  printf 'Plan only. To roll back, re-run with --yes, or run:\n  (cd mobile && %s)\n' "${cmd[*]}"
  exit 0
fi
"${cmd[@]}"
echo "Rolled back $group. Check Sentry (filter by release) and the north-star funnel over the next hours."
