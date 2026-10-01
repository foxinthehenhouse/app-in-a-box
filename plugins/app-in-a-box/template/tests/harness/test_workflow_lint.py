"""Lint for the GitHub Actions defect classes that shipped with green CI.

Ported from Forge (PUL-332, PUL-358), where every rule below is a bug that reached
main because nothing could see it; the workflow only failed when it finally ran:

  - `--allowedTools ...` in claude_args: every run died at ~300ms, 0 turns, $0
  - `--max-turns 40`: review-sized work ran out of turns
  - missing `id-token: write`: claude-code-action can't fetch its OIDC token
  - `anthropic_api_key`: the repo key never authenticated (use the OAuth token)
  - no `vars.ENABLE_*` gate: adding a secret silently starts billing every PR
  - `A && (B) || (C)` in a job `if:`: the kill switch gated one branch only
  - `gh workflow run` with `actions: read`: 403
  - a scheduled workflow with no `workflow_dispatch`: can't be re-run or tested
  - a workflow merging PRs itself (`gh pr merge`): only the review gate merges
  - a PR review that SKIPPED (the action skips PRs that edit its own workflow)
    reads as success unless a step checks `outputs.execution_file`; that step must
    run on `!cancelled()`, not `always()`; and `allowed_bots` must be set
Plus least-privilege and hygiene rules for this template: an explicit top-level
`permissions:`, no `write-all`, `timeout-minutes` on every job, `concurrency` on PR
workflows, no `pull_request_target`, and third-party actions pinned to a full SHA.

actionlint (syntax, expressions, shell) and zizmor (security) run in
workflow-lint.yml; this file is the part neither knows about. Every rule has a
negative control, so the lint is proven able to fail.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness_lib import WORKFLOWS

MIN_TURNS = 100
CLAUDE_ACTION = "anthropics/claude-code-action"
SHA_PIN = re.compile(r"@[0-9a-f]{40}$")
FIRST_PARTY = ("actions/", "github/")


def _on(doc: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML (YAML 1.1) parses the bare key `on` as boolean True.
    trig = doc.get("on", doc.get(True, {}))
    if isinstance(trig, (str, list)):
        trig = {t: None for t in ([trig] if isinstance(trig, str) else trig)}
    return trig or {}


def _perms(doc: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    # A job-level block REPLACES the workflow-level one entirely.
    own = job.get("permissions")
    if isinstance(own, dict):
        return own
    top = doc.get("permissions")
    return top if isinstance(top, dict) else {}


def _top_level_mixed_and_or(expr: str) -> bool:
    s = re.sub(r"'[^']*'", "''", expr.replace("${{", "").replace("}}", ""))
    depth, ands, ors, i = 0, False, False, 0
    while i < len(s):
        c = s[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and s.startswith("&&", i):
            ands, i = True, i + 1
        elif depth == 0 and s.startswith("||", i):
            ors, i = True, i + 1
        i += 1
    return ands and ors


def lint(doc: dict[str, Any], name: str = "workflow", raw: str = "") -> list[str]:
    problems: list[str] = []
    trig = _on(doc)
    raw = raw or json.dumps(doc)
    if "schedule" in trig and "workflow_dispatch" not in trig:
        problems.append(f"{name}: scheduled but no workflow_dispatch (cannot be re-run by hand)")
    if "permissions" not in doc:
        problems.append(f"{name}: no top-level `permissions:` (defaults can be read/write-all)")
    if "pull_request_target" in trig:
        problems.append(
            f"{name}: pull_request_target runs fork code with secrets; use pull_request"
        )
    if "pull_request" in trig and "concurrency" not in doc:
        problems.append(f"{name}: PR workflow without `concurrency` (stale runs burn minutes)")
    for jid, job in (doc.get("jobs") or {}).items():
        where = f"{name}:{jid}"
        perms = _perms(doc, job)
        if doc.get("permissions") in ("write-all",) or job.get("permissions") == "write-all":
            problems.append(f"{where}: permissions write-all")
        if "uses" not in job and "timeout-minutes" not in job:
            problems.append(f"{where}: no timeout-minutes (a hung job burns 6 hours)")
        cond = job.get("if")
        if isinstance(cond, str) and _top_level_mixed_and_or(cond):
            problems.append(
                f"{where}: `if:` mixes && and || at top level; parenthesise the || branches"
            )
        steps = job.get("steps") or []
        runs = " ".join(str(s.get("run", "")) for s in steps)
        if "gh workflow run" in runs and perms.get("actions") != "write":
            problems.append(f"{where}: runs `gh workflow run` without `actions: write` (403)")
        if re.search(r"\bgh\s+pr\s+merge\b", runs):
            problems.append(f"{where}: a workflow runs `gh pr merge`; only the review gate merges")
        for st in steps:
            uses = str(st.get("uses", ""))
            if (
                uses
                and not uses.startswith(("./", "docker://"))
                and not uses.startswith(FIRST_PARTY)
            ):
                if not SHA_PIN.search(uses):
                    problems.append(
                        f"{where}: third-party action `{uses}` is not pinned to a full SHA"
                    )
        claude_steps = [s for s in steps if str(s.get("uses", "")).startswith(CLAUDE_ACTION)]
        if not claude_steps:
            continue
        if "pull_request" in trig:
            later = " ".join(str(s.get("run", "")) + json.dumps(s.get("env") or {}) for s in steps)
            if "execution_file" not in later:
                problems.append(
                    f"{where}: PR-gate claude-code-action with no step checking "
                    "outputs.execution_file; a skipped review reads as a pass"
                )
            for st in steps:
                blob = str(st.get("run", "")) + json.dumps(st.get("env") or {})
                if "execution_file" in blob and "always()" in str(st.get("if", "")):
                    problems.append(
                        f"{where}: review-verify step runs on `always()`, so a CANCELLED review "
                        "is reported as never-run; use `!cancelled()`"
                    )
        if "secrets.CLAUDE_CODE_OAUTH_TOKEN" not in raw and "secrets.ANTHROPIC_API_KEY" not in raw:
            problems.append(f"{where}: claude-code-action with no auth secret")
        if "vars.ENABLE_" not in str(job.get("if", "")):
            problems.append(
                f"{where}: claude-code-action not gated on a vars.ENABLE_* variable (billing)"
            )
        if perms.get("id-token") != "write":
            problems.append(f"{where}: claude-code-action without `id-token: write` (OIDC failure)")
        for st in claude_steps:
            w = st.get("with") or {}
            args = str(w.get("claude_args", ""))
            if re.search(r"--allowed-?tools", args, re.I):
                problems.append(f"{where}: claude_args sets --allowedTools (killed every run)")
            m = re.search(r"--max-turns\s+(\d+)", args)
            if m and int(m.group(1)) < MIN_TURNS:
                problems.append(f"{where}: --max-turns {m.group(1)} < {MIN_TURNS}")
            if "anthropic_api_key" in w:
                problems.append(f"{where}: uses anthropic_api_key; use claude_code_oauth_token")
            if "pull_request" in trig and not w.get("allowed_bots"):
                problems.append(
                    f"{where}: claude-code-action on pull_request without `allowed_bots`"
                )
    return problems


def test_there_are_workflows() -> None:
    names = {p.name for p in WORKFLOWS}
    assert {"ci.yml", "workflow-lint.yml", "security.yml", "db.yml"} <= names, names


def test_a_claude_workflow_is_linted() -> None:
    """A guard aimed at nothing is worse than no guard: the Claude rules need a target."""
    assert any(CLAUDE_ACTION in p.read_text() for p in WORKFLOWS)


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_lint_clean(wf: Path) -> None:
    raw = wf.read_text(encoding="utf-8")
    problems = lint(yaml.safe_load(raw), wf.name, raw)
    assert not problems, "\n".join(problems)


# ---- negative controls: each rule must be able to fail -------------------------

VERIFY = {"run": 'test -n "$EXEC"', "env": {"EXEC": "${{ steps.review.outputs.execution_file }}"}}
PIN = "@" + "a" * 40
AUTH = {"claude_code_oauth_token": "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"}


def _action_doc(
    with_: dict | None = None,
    perms: dict | None = None,
    if_: str = "vars.ENABLE_CLAUDE_REVIEW == 'true'",
    **job: Any,
) -> dict:
    w = {"allowed_bots": "claude", "claude_args": "--max-turns 120", **AUTH, **(with_ or {})}
    j = {"if": if_, "timeout-minutes": 30, **job}
    j.setdefault("steps", [{"uses": CLAUDE_ACTION + PIN, "with": w}, VERIFY])
    return {
        "on": {"pull_request": None},
        "concurrency": {"group": "x"},
        "permissions": {"id-token": "write"} if perms is None else perms,
        "jobs": {"j": j},
    }


def test_clean_claude_workflow_passes() -> None:
    assert lint(_action_doc()) == []


def _base(**kw: Any) -> dict:
    return {"on": {"push": None}, "permissions": {}, **kw}


CASES: list[tuple[dict[Any, Any], str]] = [
    (_action_doc({"claude_args": "--max-turns 120 --allowedTools Bash,Read"}), "allowedTools"),
    (_action_doc({"claude_args": "--max-turns 40"}), "--max-turns 40"),
    (_action_doc({"anthropic_api_key": "x"}), "anthropic_api_key"),
    (_action_doc(perms={}), "id-token"),
    (_action_doc(if_="github.event.pull_request.draft == false"), "vars.ENABLE_"),
    (_action_doc({"claude_code_oauth_token": "hardcoded"}), "no auth secret"),
    (_action_doc({"allowed_bots": ""}), "allowed_bots"),
    (_action_doc(steps=[{"uses": CLAUDE_ACTION + PIN, "with": {"allowed_bots": "c", **AUTH}}]), "execution_file"),
    (_action_doc(steps=[{"uses": CLAUDE_ACTION + PIN, "with": {"allowed_bots": "c", **AUTH}}, {**VERIFY, "if": "always()"}]), "!cancelled()"),
    (_action_doc(steps=[{"uses": CLAUDE_ACTION + "@v1", "with": {"allowed_bots": "c", **AUTH}}, VERIFY]), "full SHA"),
    ({"on": {"schedule": [{"cron": "0 0 * * 0"}]}, "permissions": {}, "jobs": {}}, "workflow_dispatch"),
    ({"on": {"push": None}, "jobs": {}}, "no top-level `permissions:`"),
    (_base(jobs={"j": {"steps": []}}), "timeout-minutes"),
    (_base(jobs={"j": {"timeout-minutes": 5, "permissions": {"actions": "read"}, "steps": [{"run": "gh workflow run ci.yml"}]}}), "actions: write"),
    (_base(jobs={"j": {"timeout-minutes": 5, "if": "vars.X == 'true' && (a) || (b)", "steps": []}}), "mixes && and ||"),
    (_base(jobs={"j": {"timeout-minutes": 5, "steps": [{"run": 'gh pr merge "$PR" --squash'}]}}), "gh pr merge"),
    ({"on": {"pull_request_target": None}, "permissions": {}, "jobs": {}}, "pull_request_target"),
    ({"on": {"pull_request": None}, "permissions": {}, "jobs": {}}, "concurrency"),
    (_base(permissions="write-all", jobs={"j": {"timeout-minutes": 5, "steps": []}}), "write-all"),
    (_base(jobs={"j": {"timeout-minutes": 5, "steps": [{"uses": "someone/thing@v2"}]}}), "full SHA"),
]  # fmt: skip


@pytest.mark.parametrize(
    "doc, needle",
    CASES,
    ids=[
        "allowedTools", "max-turns", "api-key", "id-token", "enable-var", "auth-secret",
        "allowed-bots", "skipped-review-reads-as-pass", "verify-on-cancelled", "unpinned-claude",
        "dispatch", "permissions", "timeout", "actions-write", "if-precedence", "workflow-merges",
        "pr-target", "concurrency", "write-all", "unpinned-third-party",
    ],
)  # fmt: skip
def test_each_rule_can_fail(doc: dict, needle: str) -> None:
    problems = lint(doc)
    assert any(needle in p for p in problems), f"rule did not fire for {needle!r}: {problems}"


def test_first_party_actions_may_use_a_version_tag() -> None:
    doc = _base(jobs={"j": {"timeout-minutes": 5, "steps": [{"uses": "actions/checkout@v7"}]}})
    assert lint(doc) == []


def test_correct_if_grouping_passes() -> None:
    doc = _base(
        jobs={"j": {"timeout-minutes": 5, "if": "vars.X == 'true' && ((a) || (b))", "steps": []}}
    )
    assert lint(doc) == []
