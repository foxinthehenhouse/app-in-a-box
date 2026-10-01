#!/usr/bin/env python3
"""Read a PR's state and print the ONE next action the `land` skill should take.

    python3 .agents/skills/land/land.py            # the PR for the current branch
    python3 .agents/skills/land/land.py 42         # a specific PR
    python3 .agents/skills/land/land.py 42 --merge-ok   # the owner said "merge it when it's green"

The skill does the work (fix, reply, push); this script only decides what comes next,
in a fixed order, so the loop is the same every time and testable without a network:

    done          merged or closed
    resolve_conflict  the base moved and the PR conflicts
    fix_ci        a check failed on the current head (root-cause it; never skip a test)
    address_threads   unresolved review threads (fix + resolve, or reply why not)
    wait_ci       checks still running on the current head
    review        no pr-review verdict for THIS head yet (a push invalidates the last one)
    fix_findings  the verdict for this head is ❌ Not ready
    mark_ready    everything is green but the PR is a draft (drafts never merge)
    ask_owner     green, but the merge is the owner's call (⚠️ verdict, changes requested,
                  or they haven't said review-and-merge is OK)
    merge         green, reviewed ✅ on this head, owner opted in: squash-merge
    blocked       something this script can't read (no gh, no PR); the reason says what

Prints JSON. Standard library only. The verdict is found by the marker pr-review puts in
its comment: <!-- appbox-verdict sha=<head sha> result=safe|owner|not-ready -->
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

PR_FIELDS = (
    "number,url,state,isDraft,mergeable,headRefOid,headRefName,baseRefName,"
    "reviewDecision,statusCheckRollup,comments"
)
THREADS_QUERY = """query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){
pullRequest(number:$n){reviewThreads(first:100){nodes{isResolved isOutdated path line
comments(last:1){nodes{author{login} body url}}}}}}}"""
VERDICT = re.compile(r"<!--\s*appbox-verdict\s+sha=([0-9a-f]{7,40})\s+result=(safe|owner|not-ready)\s*-->")
FAILED = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
PENDING = {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED", "EXPECTED"}


def checks(rollup: list[dict]) -> tuple[list[dict], list[str]]:
    """(failed checks, pending check names) from gh's statusCheckRollup."""
    failed, pending = [], []
    for c in rollup or []:
        name = c.get("name") or c.get("context") or "?"
        if c.get("__typename") == "StatusContext" or "state" in c:
            state = (c.get("state") or "").upper()
            if state in FAILED:
                failed.append({"name": name, "url": c.get("targetUrl")})
            elif state in PENDING:
                pending.append(name)
            continue
        if (c.get("status") or "").upper() != "COMPLETED":
            pending.append(name)
        elif (c.get("conclusion") or "").upper() in FAILED:
            failed.append({"name": name, "url": c.get("detailsUrl")})
    return failed, pending


def verdict_for(comments: list[dict], head: str) -> str | None:
    """The newest pr-review verdict recorded for this exact head commit."""
    found = None
    for c in comments or []:
        for sha, result in VERDICT.findall(c.get("body") or ""):
            if head and head.startswith(sha):  # full or abbreviated (>= 7) sha of this head
                found = result
    return found


def decide(pr: dict, threads: list[dict], merge_ok: bool = False) -> dict:
    """The pure part: PR state in, one action out. Order is the contract."""
    out = {"pr": pr.get("number"), "url": pr.get("url"), "head": pr.get("headRefOid")}
    state = (pr.get("state") or "").upper()
    if state in ("MERGED", "CLOSED"):
        return {**out, "action": "done", "reason": f"the PR is {state.lower()}"}
    if (pr.get("mergeable") or "").upper() == "CONFLICTING":
        return {**out, "action": "resolve_conflict",
                "reason": f"conflicts with {pr.get('baseRefName')}: merge it in (no rebase or force-push on a shared branch)"}
    failed, pending = checks(pr.get("statusCheckRollup") or [])
    if failed:
        return {**out, "action": "fix_ci", "reason": f"{len(failed)} check(s) failed on this head", "items": failed}
    open_threads = [
        {"path": t.get("path"), "line": t.get("line"), "outdated": t.get("isOutdated", False),
         "author": ((t.get("comments") or {}).get("nodes") or [{}])[-1].get("author", {}).get("login"),
         "url": ((t.get("comments") or {}).get("nodes") or [{}])[-1].get("url")}
        for t in threads if not t.get("isResolved")
    ]
    if open_threads:
        return {**out, "action": "address_threads", "reason": f"{len(open_threads)} unresolved review thread(s)", "items": open_threads}
    if pending:
        return {**out, "action": "wait_ci", "reason": "checks still running on this head", "items": pending}
    v = verdict_for(pr.get("comments") or [], pr.get("headRefOid") or "")
    if v is None:
        return {**out, "action": "review", "reason": "no pr-review verdict for this head yet (a push invalidates the last one)"}
    if v == "not-ready":
        return {**out, "action": "fix_findings", "reason": "pr-review said ❌ Not ready for this head"}
    if pr.get("isDraft"):
        return {**out, "action": "mark_ready", "reason": "green and reviewed, but a draft (drafts never merge)"}
    if (pr.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED":
        return {**out, "action": "ask_owner", "reason": "a reviewer requested changes: re-request their review after addressing them"}
    if v == "owner":
        return {**out, "action": "ask_owner", "reason": "pr-review said ⚠️ merge after owner decision"}
    if not merge_ok:
        return {**out, "action": "ask_owner", "reason": "green and ✅, but the owner hasn't said to merge"}
    return {**out, "action": "merge", "reason": "green, ✅ on this head, owner opted in: squash-merge and delete the branch"}


def gh(*args: str) -> str | None:
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    merge_ok = "--merge-ok" in argv
    raw = gh("pr", "view", *(args[:1]), "--json", PR_FIELDS)
    if raw is None:
        print(json.dumps({"action": "blocked", "reason": "gh couldn't read the PR (not installed, not logged in, or no PR for this branch)"}))
        return 0
    pr = json.loads(raw)
    repo = json.loads(gh("repo", "view", "--json", "owner,name") or "{}")
    threads: list[dict] = []
    if repo:
        t = gh("api", "graphql", "-f", f"query={THREADS_QUERY}", "-F", f"o={repo['owner']['login']}",
               "-F", f"r={repo['name']}", "-F", f"n={pr['number']}")
        if t:
            data = json.loads(t)
            threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    print(json.dumps(decide(pr, threads, merge_ok), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
