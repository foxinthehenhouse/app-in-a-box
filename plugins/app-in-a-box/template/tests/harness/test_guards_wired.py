"""Every guard this repo claims is actually wired, and able to fail the build.

Ported (simplified) from a real app's guard-wiring test. A guard fails silently in
three ways, each checked here with a negative control:

1. **Unwired.** A `scripts/check_*.py` or `mobile/scripts/check-*.js` that no workflow,
   git hook or `npm run gates` ever runs is dead weight that reads as coverage.
2. **Advisory.** A guard step behind `continue-on-error: true` or ending `|| true` runs,
   goes red, and the build stays green. Allowed only when declared in ADVISORY with a
   reason (the dict only ratchets down).
3. **Deselected.** pytest guards are wired by pyproject's `testpaths`; narrowing it or
   adding `--ignore`/`--deselect`/`-k` to `addopts` silently unwires a whole family.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness_lib import ROOT, WORKFLOWS

# workflow file -> why its guard steps may not fail the build. Shrink, don't grow.
ADVISORY: dict[str, str] = {}
# guard file -> why no workflow runs it. Shrink, don't grow.
UNWIRED: dict[str, str] = {}

_SETUP_ACTION = re.compile(
    r"^(actions/(checkout|setup-[a-z]+|cache|upload-artifact)|github/codeql-action/init)@"
)
_SETUP_RUN = re.compile(
    r"^(npm\s+(ci|install)|pip3?\s+install|python3?\s+-m\s+pip\s+install|sudo\s+apt-get|curl\s|tar\s|echo\s|mkdir\s)"
)
_SWALLOW = re.compile(r"\|\|\s*(true|:|exit\s+0)\s*$")


def guard_files(root: Path) -> list[str]:
    found = [p.name for p in (root / "scripts").glob("check_*.py")]
    found += [p.name for p in (root / "scripts").glob("db-test.sh")]
    # The mobile guards are wired through `npm run gates` in mobile/package.json, which
    # the scaffold phase creates (create-expo-app). Before that there is no app to gate.
    if (root / "mobile" / "package.json").exists():
        found += [p.name for p in (root / "mobile" / "scripts").glob("check-*.js")]
    return sorted(found)


def wiring_text(root: Path) -> str:
    """Everything that can RUN a guard: workflows, git hooks, npm scripts."""
    parts = [p.read_text(encoding="utf-8") for p in (root / ".github" / "workflows").glob("*.y*ml")]
    parts += [p.read_text(encoding="utf-8") for p in (root / ".githooks").glob("*") if p.is_file()]
    pkg = root / "mobile" / "package.json"
    if pkg.exists():
        parts.append(json.dumps(json.loads(pkg.read_text()).get("scripts", {})))
    text = "\n".join(parts)
    # One level of indirection: a shell script that is itself run by the above (e.g.
    # db.yml -> scripts/db-test.sh -> check_migration_versions.py) wires what it runs.
    for sh in sorted((root / "scripts").glob("*.sh")):
        if sh.name in text:
            text += "\n" + sh.read_text(encoding="utf-8")
    return text


def _shell_lines(run: str) -> list[str]:
    out, buf = [], ""
    for raw in run.splitlines():
        line = raw.strip()
        if not buf and (not line or line.startswith("#")):
            continue
        line = re.sub(r"\s+#.*$", "", line)
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        out.append(buf + line)
        buf = ""
    return out + ([buf] if buf else [])


def _is_guard(step: dict[str, Any]) -> bool:
    uses = str(step.get("uses") or "")
    if uses:
        return not _SETUP_ACTION.match(uses)
    lines = _shell_lines(str(step.get("run") or ""))
    return bool(lines) and not all(_SETUP_RUN.match(ln) for ln in lines)


def _suppressed(node: dict[str, Any]) -> bool:
    value = node.get("continue-on-error", False)
    return value is not False and str(value).strip().lower() not in {"false", ""}


def advisory_steps(doc: dict[str, Any]) -> list[str]:
    """Guard steps in one workflow that cannot fail the build."""
    found = []
    for jid, job in (doc.get("jobs") or {}).items():
        steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
        if _suppressed(job) and any(_is_guard(s) for s in steps):
            found.append(f"job {jid}: continue-on-error")
        for i, st in enumerate(steps):
            label = f"job {jid} step {st.get('name') or i}"
            if _suppressed(st) and _is_guard(st):
                found.append(f"{label}: continue-on-error")
            for line in _shell_lines(str(st.get("run") or "")):
                if _SWALLOW.search(line) and _is_guard({"run": _SWALLOW.sub("", line)}):
                    found.append(f"{label}: `{line[:70]}`")
    return found


def collection_problems(pyproject: dict[str, Any]) -> list[str]:
    opts = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    problems = []
    if opts.get("testpaths") != ["tests"]:
        problems.append(f"testpaths narrowed to {opts.get('testpaths')}")
    if re.search(r"--ignore|--deselect|(^|\s)-k\s", str(opts.get("addopts", ""))):
        problems.append(f"addopts deselects tests: {opts.get('addopts')!r}")
    return problems


# ---- the real repo ---------------------------------------------------------------


def test_discovery_is_not_vacuous() -> None:
    assert len(guard_files(ROOT)) >= 2, guard_files(ROOT)
    assert len(WORKFLOWS) >= 4


def test_every_guard_is_run_by_something() -> None:
    text = wiring_text(ROOT)
    unwired = [g for g in guard_files(ROOT) if g not in text and g not in UNWIRED]
    assert not unwired, f"guards no workflow, git hook or npm script runs: {unwired}"


def test_ci_runs_the_mobile_gates_and_the_harness() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "npm run gates" in ci, "ci.yml no longer runs the mobile gates"
    assert "pytest" in ci and "pyright" in ci and "ruff" in ci


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_guard_step_is_silently_advisory(wf: Path) -> None:
    found = advisory_steps(yaml.safe_load(wf.read_text()))
    if wf.name in ADVISORY:
        assert found, f"{wf.name} is declared ADVISORY but has no suppression; remove it"
        return
    assert not found, f"{wf.name} has guard steps that cannot fail the build: {found}"


def test_escape_hatches_have_reasons() -> None:
    for key, reason in {**ADVISORY, **UNWIRED}.items():
        assert len(reason.strip()) > 20, f"{key}: say why, or fix it"


def test_pytest_collection_is_not_narrowed() -> None:
    problems = collection_problems(tomllib.loads((ROOT / "pyproject.toml").read_text()))
    assert not problems, problems


@pytest.mark.parametrize(
    "guard",
    [
        "tests/test_wire_contract.py",
        "tests/test_scoping_static.py",
        "tests/test_migrations_static.py",
        "tests/harness/test_workflow_lint.py",
        "tests/harness/test_skills_lint.py",
        "tests/harness/test_hook_scripts.py",
        "tests/harness/test_supply_chain.py",
        "supabase/tests/database/rls.test.sql",
    ],
)
def test_named_guards_still_exist(guard: str) -> None:
    """Collection is automatic, so the risk is a guard quietly deleted, not unwired."""
    assert (ROOT / guard).exists(), f"{guard} is gone; if retired on purpose, say so here"


# ---- negative controls -----------------------------------------------------------


def test_unwired_guard_is_caught(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_thing.py").write_text("")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("jobs: {}\n")
    assert guard_files(tmp_path) == ["check_thing.py"]
    assert "check_thing.py" not in wiring_text(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "run: python3 scripts/check_thing.py\n"
    )
    assert "check_thing.py" in wiring_text(tmp_path)
    assert "check-x.js" not in guard_files(tmp_path)
    (tmp_path / "mobile" / "scripts").mkdir(parents=True)
    (tmp_path / "mobile" / "scripts" / "check-x.js").write_text("")
    (tmp_path / "mobile" / "package.json").write_text('{"scripts": {"gates": "tsc"}}')
    assert "check-x.js" in guard_files(tmp_path)
    assert "check-x.js" not in wiring_text(tmp_path)


@pytest.mark.parametrize(
    "doc",
    [
        {"jobs": {"j": {"steps": [{"run": "pytest -q", "continue-on-error": True}]}}},
        {"jobs": {"j": {"continue-on-error": True, "steps": [{"run": "ruff check ."}]}}},
        {"jobs": {"j": {"steps": [{"run": "gitleaks detect || true"}]}}},
        {
            "jobs": {
                "j": {
                    "steps": [{"uses": "some/scanner@" + "a" * 40, "continue-on-error": "${{ x }}"}]
                }
            }
        },
    ],
    ids=["step-coe", "job-coe", "or-true", "coe-expression"],
)
def test_advisory_suppression_is_caught(doc: dict) -> None:
    assert advisory_steps(doc)


def test_setup_steps_may_be_lenient() -> None:
    doc = {
        "jobs": {
            "j": {"steps": [{"run": "pip install x || true"}, {"uses": "actions/checkout@v7"}]}
        }
    }
    assert advisory_steps(doc) == []


def test_collection_narrowing_is_caught() -> None:
    bad = {
        "tool": {
            "pytest": {
                "ini_options": {"testpaths": ["tests/unit"], "addopts": "--ignore=tests/harness"}
            }
        }
    }
    assert len(collection_problems(bad)) == 2
    good = {
        "tool": {
            "pytest": {"ini_options": {"testpaths": ["tests"], "addopts": "-m 'not integration'"}}
        }
    }
    assert collection_problems(good) == []
