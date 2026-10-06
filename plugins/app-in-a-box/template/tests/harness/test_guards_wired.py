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

The architecture boundaries (`lint-imports`, contracts in pyproject's `[tool.importlinter]`)
are checked the same way: CI must run it, and the two contracts must still say what
AGENTS.md says they do.
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
    found += [p.name for p in (root / "scripts").glob("db-*.sh")]  # db-test.sh, db-lint.sh
    # Not named check_*, but a guard all the same: `--check` fails on a drifted DESIGN.md.
    found += [p.name for p in (root / "scripts").glob("design_md.py")]
    # Same for the Accessibility Nutrition Labels: `--check` fails on a claim without evidence.
    found += [p.name for p in (root / "scripts").glob("a11y_labels.py")]
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


def boundary_problems(pyproject: dict[str, Any]) -> list[str]:
    """The import-linter contracts AGENTS.md points at: still present, still meaningful."""
    cfg = pyproject.get("tool", {}).get("importlinter", {})
    contracts = cfg.get("contracts", [])
    problems = []
    if cfg.get("root_package") != "backend":
        problems.append(f"root_package is {cfg.get('root_package')!r}, not 'backend'")
    layers = [c for c in contracts if c.get("type") == "layers"]
    order = layers[0].get("layers", []) if layers else []
    wanted = ["routers", "services", "db"]
    if [x for x in order if x in wanted] != wanted:
        problems.append(f"no layers contract with routers above services above db: {order}")
    fence = [c for c in contracts if c.get("type") == "forbidden"]
    if not fence or not {"anthropic", "openai"} <= set(fence[0].get("forbidden_modules", [])):
        problems.append("no forbidden contract fencing the anthropic and openai SDKs")
    elif not cfg.get("include_external_packages"):
        problems.append("include_external_packages is off, so the SDK fence can never fail")
    elif fence[0].get("allow_indirect_imports") or fence[0].get("source_modules") != ["backend"]:
        problems.append(f"the SDK fence was narrowed: {fence[0]}")
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
    assert "pytest" in ci
    assert "pyright" in ci
    assert "ruff" in ci
    assert "run: lint-imports" in ci, "ci.yml no longer checks the architecture boundaries"


def test_architecture_boundaries_are_still_contracts() -> None:
    problems = boundary_problems(tomllib.loads((ROOT / "pyproject.toml").read_text()))
    assert not problems, problems


def design_md_wired(root: Path) -> list[str]:
    """Where the DESIGN.md drift check should run but doesn't. Its mode is a flag, so
    the file name appearing (e.g. a bare regenerate) isn't enough: it must be `--check`."""
    if not (root / "scripts" / "design_md.py").exists():
        return []
    want = "python3 scripts/design_md.py --check"
    places = {"ci.yml": root / ".github" / "workflows" / "ci.yml"}
    places["pre-commit"] = root / ".githooks" / "pre-commit"
    return [n for n, p in places.items() if not p.is_file() or want not in p.read_text()]


def test_design_md_check_runs_in_ci_and_pre_commit() -> None:
    missing = design_md_wired(ROOT)
    assert not missing, f"`python3 scripts/design_md.py --check` is not run by: {missing}"


def a11y_labels_wired(root: Path) -> list[str]:
    """Where the accessibility-labels drift check should run but doesn't. CI runs it in
    the mobile job, after the gates whose passing it cites; a bare run rewrites the file
    instead of checking it, so only `--check` counts."""
    if not (root / "scripts" / "a11y_labels.py").exists():
        return []
    places = {
        "ci.yml": (
            root / ".github" / "workflows" / "ci.yml",
            "python3 ../scripts/a11y_labels.py --check",
        ),
        "pre-commit": (root / ".githooks" / "pre-commit", "python3 scripts/a11y_labels.py --check"),
    }
    return [n for n, (p, want) in places.items() if not p.is_file() or want not in p.read_text()]


def test_a11y_labels_check_runs_in_ci_and_pre_commit() -> None:
    missing = a11y_labels_wired(ROOT)
    assert not missing, f"`scripts/a11y_labels.py --check` is not run by: {missing}"
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    runs = [str(st.get("run") or "") for st in ci["jobs"]["mobile"]["steps"]]
    gates = next(i for i, r in enumerate(runs) if "npm run gates" in r)
    labels = next(i for i, r in enumerate(runs) if "a11y_labels.py --check" in r)
    assert labels > gates, "the labels check must run after the gates it cites as evidence"


def data_map_wired(root: Path) -> list[str]:
    """Where the privacy data map check should run but doesn't. `--write` regenerates the
    store answers instead of checking them, so a step running that checks nothing."""
    if not (root / "scripts" / "check_data_map.py").exists():
        return []
    places = {"ci.yml": root / ".github" / "workflows" / "ci.yml"}
    places["pre-commit"] = root / ".githooks" / "pre-commit"
    missing = []
    for name, path in places.items():
        text = path.read_text() if path.is_file() else ""
        runs = [ln for ln in text.splitlines() if "scripts/check_data_map.py" in ln]
        if not runs or any("--write" in ln for ln in runs):
            missing.append(name)
    return missing


def test_data_map_check_runs_in_ci_and_pre_commit() -> None:
    missing = data_map_wired(ROOT)
    assert not missing, f"`scripts/check_data_map.py` (the check, not --write) is not run by: {missing}"


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
        "tests/test_idempotency.py",
        "tests/test_outbound_http.py",
        "tests/harness/test_workflow_lint.py",
        "tests/harness/test_skills_lint.py",
        "tests/harness/test_hook_scripts.py",
        "tests/harness/test_supply_chain.py",
        "tests/test_data_map.py",
        "privacy/data-map.yaml",
        "supabase/tests/database/rls.test.sql",
        "supabase/ci/schema_snapshot.sql",
        "supabase/schema-snapshot.txt",
        ".squawk.toml",
        "tests/harness/test_code_health.py",
        ".github/CODEOWNERS",
        "mobile/knip.jsonc",
        "tests/test_a11y_labels.py",
        "mobile/__tests__/a11y-screens.test.tsx",
        "mobile/scripts/__tests__/check-a11y.test.js",
    ],
)
def test_named_guards_still_exist(guard: str) -> None:
    """Collection is automatic, so the risk is a guard quietly deleted, not unwired."""
    assert (ROOT / guard).exists(), f"{guard} is gone; if retired on purpose, say so here"


# Squawk rules a Supabase app must keep: each is a migration that locks or breaks a live
# database (the expand/contract rule in .agents/rules/db-migrations.md, enforced).
SQUAWK_MUST_KEEP = {
    "require-concurrent-index-creation",
    "adding-required-field",
    "renaming-column",
    "ban-drop-column",
    "ban-drop-table",
    "changing-column-type",
    "adding-not-nullable-field",
}


def squawk_problems(text: str) -> list[str]:
    """What is wrong with a .squawk.toml: a must-keep rule excluded, or an exclusion
    with no comment saying why."""
    excluded = tomllib.loads(text).get("excluded_rules", [])
    problems = [f"{r} must stay on" for r in excluded if r in SQUAWK_MUST_KEEP]
    comments = "\n".join(ln for ln in text.splitlines() if ln.lstrip().startswith("#"))
    problems += [f"{r} is excluded with no reason" for r in excluded if r not in comments]
    return problems


def test_db_workflow_lints_migrations_with_pinned_squawk() -> None:
    # A step must RUN it: the file's header comment names it too, so grep isn't enough.
    db = yaml.safe_load((ROOT / ".github" / "workflows" / "db.yml").read_text())
    runs = [str(s.get("run") or "") for j in db["jobs"].values() for s in j.get("steps", [])]
    assert any("scripts/db-lint.sh" in r for r in runs), (
        "db.yml no longer runs the migration linter"
    )
    lint = (ROOT / "scripts" / "db-lint.sh").read_text()
    assert re.search(r'^SQUAWK_VERSION="\d+\.\d+\.\d+"$', lint, re.M), "pin squawk"
    assert "--config .squawk.toml" in lint
    assert "schema_snapshot.sql" in (ROOT / "scripts" / "db-test.sh").read_text()


def test_squawk_config_keeps_the_live_database_rules() -> None:
    problems = squawk_problems((ROOT / ".squawk.toml").read_text())
    assert not problems, problems


# ---- negative controls -----------------------------------------------------------


def test_weakened_squawk_config_is_caught() -> None:
    assert squawk_problems('excluded_rules = ["renaming-column"]\n# renaming-column: meh\n') == [
        "renaming-column must stay on"
    ]
    assert squawk_problems('excluded_rules = ["prefer-identity"]\n') == [
        "prefer-identity is excluded with no reason"
    ]
    assert (
        squawk_problems('# prefer-identity: we use uuid\nexcluded_rules = ["prefer-identity"]\n')
        == []
    )


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
    (tmp_path / "scripts" / "db-lint.sh").write_text("squawk\n")
    assert "db-lint.sh" in guard_files(tmp_path)
    assert "db-lint.sh" not in wiring_text(tmp_path)
    assert "check-x.js" not in guard_files(tmp_path)
    (tmp_path / "mobile" / "scripts").mkdir(parents=True)
    (tmp_path / "mobile" / "scripts" / "check-x.js").write_text("")
    (tmp_path / "mobile" / "package.json").write_text('{"scripts": {"gates": "tsc"}}')
    assert "check-x.js" in guard_files(tmp_path)
    assert "check-x.js" not in wiring_text(tmp_path)


def test_unwired_design_md_check_is_caught(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "design_md.py").write_text("")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".githooks").mkdir()
    ci = tmp_path / ".github" / "workflows" / "ci.yml"
    hook = tmp_path / ".githooks" / "pre-commit"
    ci.write_text("run: python3 scripts/design_md.py\n")  # regenerates; checks nothing
    hook.write_text("python3 scripts/design_md.py --check\n")
    assert "design_md.py" in guard_files(tmp_path)
    assert design_md_wired(tmp_path) == ["ci.yml"]
    ci.write_text("run: python3 scripts/design_md.py --check\n")
    assert design_md_wired(tmp_path) == []


def test_unwired_a11y_labels_check_is_caught(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a11y_labels.py").write_text("")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".githooks").mkdir()
    ci = tmp_path / ".github" / "workflows" / "ci.yml"
    hook = tmp_path / ".githooks" / "pre-commit"
    ci.write_text("run: python3 ../scripts/a11y_labels.py\n")  # rewrites; checks nothing
    hook.write_text("python3 scripts/a11y_labels.py --check\n")
    assert "a11y_labels.py" in guard_files(tmp_path)
    assert a11y_labels_wired(tmp_path) == ["ci.yml"]
    ci.write_text("run: python3 ../scripts/a11y_labels.py --check\n")
    assert a11y_labels_wired(tmp_path) == []
    hook.write_text("echo nothing\n")
    assert a11y_labels_wired(tmp_path) == ["pre-commit"]


def test_unwired_data_map_check_is_caught(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check_data_map.py").write_text("")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".githooks").mkdir()
    ci = tmp_path / ".github" / "workflows" / "ci.yml"
    hook = tmp_path / ".githooks" / "pre-commit"
    ci.write_text("run: python scripts/check_data_map.py --write\n")  # regenerates; checks nothing
    hook.write_text('"$py" scripts/check_data_map.py\n')
    assert data_map_wired(tmp_path) == ["ci.yml"]
    ci.write_text("run: python scripts/check_data_map.py\n")
    assert data_map_wired(tmp_path) == []
    hook.write_text("echo nothing\n")
    assert data_map_wired(tmp_path) == ["pre-commit"]


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


@pytest.mark.parametrize(
    "edit",
    [
        lambda c: c.pop("contracts"),
        lambda c: c["contracts"][0].update(layers=["services", "routers", "db"]),
        lambda c: c["contracts"][1].update(forbidden_modules=["openai"]),
        lambda c: c.update(include_external_packages=False),
        lambda c: c["contracts"][1].update(allow_indirect_imports=True),
    ],
    ids=["no-contracts", "layers-inverted", "sdk-unfenced", "externals-off", "indirect-ok"],
)
def test_weakened_boundaries_are_caught(edit: Any) -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert boundary_problems(pyproject) == []
    edit(pyproject["tool"]["importlinter"])
    assert boundary_problems(pyproject)


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
