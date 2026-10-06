"""Supply chain: what CI installs is pinned, hashed and audited.

- Python installs come from the hashed lock files with `--require-hashes`, never from
  the ranges in requirements*.txt; scripts/check_lock.py fails when a range changes
  and the lock was not regenerated (scripts/lock-deps.sh).
- `npm ci` runs no install scripts.
- security.yml audits both ecosystems and uploads an SBOM.
- scripts/check_npm_audit.py fails on untriaged or expired high/critical advisories.

Dependabot's cooldown is checked with the rest of dependabot.yml, in
test_config_schemas.py. Every rule here has a negative control below it.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import re
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from harness_lib import ROOT, WORKFLOWS


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec
    assert spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check_lock = _load("check_lock")
check_npm_audit = _load("check_npm_audit")

_PIP = re.compile(r"\bpip3?\s+install\b(.*)")
_NPM_CI = re.compile(r"\bnpm\s+ci\b(.*)")


def install_problems(text: str, where: str) -> list[str]:
    """Unhashed pip installs and script-running `npm ci` in one workflow's text."""
    problems = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if m := _PIP.search(line):
            args = m.group(1)
            if "--require-hashes" not in args or not re.search(r"-r\s+\S+\.lock\b", args):
                problems.append(
                    f"{where}: `{line.strip()}` must install a .lock with --require-hashes"
                )
        if (m := _NPM_CI.search(line)) and "--ignore-scripts" not in m.group(1):
            problems.append(f"{where}: `{line.strip()}` runs install scripts; add --ignore-scripts")
    return problems


def audit_problems(doc: dict[str, Any]) -> list[str]:
    """What security.yml's `dependencies` job must do."""
    steps = ((doc.get("jobs") or {}).get("dependencies") or {}).get("steps") or []
    runs = "\n".join(str(s.get("run") or "") for s in steps if isinstance(s, dict))
    uses = [str(s.get("uses") or "") for s in steps if isinstance(s, dict)]
    problems = []
    if not re.search(r"pip-audit .*--require-hashes -r requirements[\w-]*\.lock", runs):
        problems.append("no pip-audit over a lock file")
    if "scripts/check_npm_audit.py" not in runs:
        problems.append("no npm audit (scripts/check_npm_audit.py)")
    if "cyclonedx" not in runs:
        problems.append("no CycloneDX SBOM")
    if not any(u.startswith("actions/upload-artifact@") for u in uses):
        problems.append("the SBOM is not uploaded as an artifact")
    return problems


# ---- the real repo ---------------------------------------------------------------


def test_locks_match_requirements() -> None:
    assert check_lock.check(ROOT) == []


def test_lock_inputs_are_the_requirement_files() -> None:
    # The check reads its inputs from LOCKS; if a requirement file is added or renamed
    # without updating it, nothing would be compared at all.
    reqs = sorted(p.name for p in ROOT.glob("requirements*.txt"))
    assert sorted({f for inputs in check_lock.LOCKS.values() for f in inputs}) == reqs


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_installs_are_hashed_and_scriptless(wf: Path) -> None:
    assert install_problems(wf.read_text(), wf.name) == []


def test_dev_venv_installs_the_lock_with_hashes() -> None:
    text = (ROOT / "scripts" / "dev-venv.sh").read_text()
    assert 'LOCK="$ROOT/requirements-dev.lock"' in text
    assert '--require-hashes -r "$LOCK"' in text


def test_security_workflow_audits_and_publishes_an_sbom() -> None:
    doc = yaml.safe_load((ROOT / ".github" / "workflows" / "security.yml").read_text())
    assert audit_problems(doc) == []


# ---- negative controls -----------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for name in ("requirements.txt", "requirements-dev.txt", *check_lock.LOCKS):
        shutil.copy(ROOT / name, tmp_path / name)
    return tmp_path


def test_a_changed_range_without_a_relock_is_caught(repo: Path) -> None:
    req = repo / "requirements.txt"
    req.write_text(req.read_text().replace("pydantic>=2.9,<3", "pydantic>=2.10,<3"))
    problems = check_lock.check(repo)
    assert any("requirements.lock is stale" in p for p in problems), problems
    assert any("requirements-dev.lock is stale" in p for p in problems), problems


def test_a_new_package_without_a_relock_is_caught(repo: Path) -> None:
    with (repo / "requirements-dev.txt").open("a") as f:
        f.write("left-pad>=1,<2\n")
    problems = check_lock.check(repo)
    assert any("`left-pad>=1,<2` is not in the lock" in p for p in problems), problems


def test_a_comment_edit_needs_no_relock(repo: Path) -> None:
    req = repo / "requirements-dev.txt"
    req.write_text("# a new comment\n" + req.read_text())
    assert check_lock.check(repo) == []


def test_a_pin_without_a_hash_is_caught(repo: Path) -> None:
    lock = repo / "requirements.lock"
    text = re.sub(r"(?m)^(fastapi==\S+) \\\n(    --hash=\S+(?: \\)?\n)+", r"\1\n", lock.read_text())
    lock.write_text(text)
    assert any("no --hash" in p and "fastapi" in p for p in check_lock.check(repo))


def test_locks_that_disagree_are_caught(repo: Path) -> None:
    lock = repo / "requirements-dev.lock"
    lock.write_text(re.sub(r"(?m)^fastapi==\S+", "fastapi==0.0.1", lock.read_text()))
    assert any("CI would test a version that does not ship" in p for p in check_lock.check(repo))


def test_a_missing_lock_is_caught(repo: Path) -> None:
    (repo / "requirements-dev.lock").unlink()
    assert any("missing requirements-dev.lock" in p for p in check_lock.check(repo))


def test_unhashed_installs_are_caught() -> None:
    bad = "run: pip install -r requirements.txt\nrun: npm ci\n"
    assert len(install_problems(bad, "x.yml")) == 2
    good = "run: python -m pip install --require-hashes -r requirements-dev.lock\n"
    assert install_problems(good + "run: npm ci --ignore-scripts\n", "x.yml") == []


def test_a_security_workflow_without_audits_is_caught() -> None:
    assert len(audit_problems({"jobs": {"gitleaks": {"steps": []}}})) == 4


ADV = {
    "auditReportVersion": 2,
    "vulnerabilities": {
        "braces": {
            "name": "braces",
            "via": [
                {
                    "name": "braces",
                    "severity": "high",
                    "title": "sig check",
                    "url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
                }
            ],
        },
        "@expo/cli": {"name": "@expo/cli", "via": ["braces"]},
        "uuid": {
            "name": "uuid",
            "via": [{"name": "uuid", "severity": "moderate", "url": "https://x/advisories/GHSA-m"}],
        },
    },
}
TODAY = dt.date(2026, 1, 1)


def _allow(**kw: Any) -> dict[str, Any]:
    entry = {
        "package": "braces",
        "reason": "build-time only, via @expo/cli",
        "until": "2026-02-01",
    }
    return {"GHSA-aaaa-bbbb-cccc": {**entry, **kw}}


def test_npm_audit_untriaged_high_fails() -> None:
    found = check_npm_audit.advisories(ADV)
    assert list(found) == ["GHSA-aaaa-bbbb-cccc"]  # moderate is not blocking
    problems, _ = check_npm_audit.check(found, {}, TODAY)
    assert problems
    assert problems[0].startswith("high GHSA-aaaa-bbbb-cccc in braces")


def test_npm_audit_triaged_passes_until_it_expires() -> None:
    found = check_npm_audit.advisories(ADV)
    assert check_npm_audit.check(found, _allow(), TODAY) == ([], [])
    problems, _ = check_npm_audit.check(found, _allow(until="2025-12-31"), TODAY)
    assert any("expired on 2025-12-31" in p for p in problems)


@pytest.mark.parametrize(
    ("entry", "needle"),
    [({"until": "2026-12-01"}, "more than 90 days"), ({"reason": "ok"}, "needs a reason")],
)
def test_npm_audit_allowlist_rules(entry: dict[str, str], needle: str) -> None:
    found = check_npm_audit.advisories(ADV)
    problems, _ = check_npm_audit.check(found, _allow(**entry), TODAY)
    assert any(needle in p for p in problems), problems


def test_npm_audit_stale_entry_is_noted_not_failed() -> None:
    problems, notes = check_npm_audit.check({}, _allow(), TODAY)
    assert problems == []
    assert "no longer reported" in notes[0]


def test_npm_audit_that_could_not_run_fails() -> None:
    with pytest.raises(ValueError, match="not an npm audit report"):
        check_npm_audit.advisories({"error": {"code": "ENOLOCK"}})
