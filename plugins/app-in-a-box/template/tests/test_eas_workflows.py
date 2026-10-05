"""EAS Workflows + eas.json, checked against the documented job schema.

EAS runs these files on Expo's servers, so a mistake only shows when a release
silently does the wrong thing: a PR preview that publishes with production env
vars, a fingerprint that never matches a build, or an iOS submit that dies for
lack of `ascAppId`, an OTA crash Sentry can't symbolicate, or a bad OTA that
reaches every user before anyone sees it crash. The rules come from the EAS
Workflows docs source (expo/expo docs/pages/eas/workflows/pre-packaged-jobs.mdx).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "mobile/.eas/workflows"
EAS_JSON = ROOT / "mobile/eas.json"
APPBOX = ROOT / "appbox.yaml"

# Documented params per pre-packaged job type (the subset this repo uses).
PARAMS = {
    "fingerprint": {"unstable_skip_cng_check"},
    "get-build": {
        "platform",
        "profile",
        "distribution",
        "channel",
        "app_identifier",
        "app_build_version",
        "app_version",
        "git_commit_hash",
        "fingerprint_hash",
        "sdk_version",
        "runtime_version",
        "simulator",
        "wait_for_in_progress",
    },
    "build": {"platform", "profile", "message", "refresh_ad_hoc_provisioning_profile"},
    "submit": {"build_id", "profile", "groups"},
    "update": {
        "message",
        "platform",
        "branch",
        "channel",
        "rollout_percentage",
        "private_key_path",
        "upload_sentry_sourcemaps",
    },
    "update-rollout": {"update_group_id", "rollout_percentage"},
    "require-approval": set(),
    "repack": {
        "build_id", "profile", "embed_bundle_assets", "js_bundle_only", "message",
        "repack_version", "repack_package", "ios_signing_use_source_app_entitlements",
        "ios_signing_app_entitlements_path",
    },
    "maestro": {
        "build_id",
        "flow_path",
        "shards",
        "retries",
        "retry_failed_only",
        "record_screen",
        "include_tags",
        "exclude_tags",
        "maestro_version",
        "android_system_image_package",
        "device_identifier",
        "output_format",
        "skip_build_check",
    },
}
OUTPUTS = {
    "fingerprint": {"android_fingerprint_hash", "ios_fingerprint_hash"},
    "get-build": {
        "build_id",
        "app_build_version",
        "app_identifier",
        "app_version",
        "channel",
        "distribution",
        "fingerprint_hash",
        "git_commit_hash",
        "platform",
    },
    "build": {
        "build_id",
        "app_build_version",
        "app_identifier",
        "app_version",
        "channel",
        "distribution",
        "fingerprint_hash",
        "git_commit_hash",
        "platform",
        "profile",
        "runtime_version",
        "sdk_version",
        "simulator",
    },
    "submit": {"apple_app_id", "ios_bundle_identifier", "android_package_id"},
    "update": {"first_update_group_id", "updates_json"},
    "update-rollout": {"update_group_id", "rollout_percentage", "updates_json"},
    "repack": {"build_id"},
}
# Jobs whose `environment` defaults to production when omitted (docs: "all other
# jobs default to production"); build infers it from the profile, submit from the build.
DEFAULTS_TO_PRODUCTION = {"fingerprint", "update", "get-build"}

NEEDS_REF = re.compile(r"needs\.([a-z0-9_]+)\.outputs\.([a-z0-9_]+)")


def _workflows() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _eas() -> dict:
    return json.loads(EAS_JSON.read_text())


def _errors_stack() -> str:
    """appbox.yaml's `stack.errors` (sentry | none); a bare render has no appbox.yaml
    yet and ships with Sentry wired."""
    if not APPBOX.is_file():
        return "sentry"
    stack = (yaml.safe_load(APPBOX.read_text()) or {}).get("stack") or {}
    return str(stack.get("errors", "sentry"))


def _profile_env(profile: str) -> str:
    return _eas()["build"][profile].get("environment", "production")


def test_workflows_exist() -> None:
    names = {p.name for p in _workflows()}
    assert {"pr-preview.yml", "release.yml"} <= names, names


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_jobs_use_documented_params_and_outputs(path: Path) -> None:
    jobs = _load(path)["jobs"]
    for job_id, job in jobs.items():
        kind = job.get("type")
        if kind is None:  # a custom steps job
            continue
        assert kind in PARAMS, f"{path.name}:{job_id}: unknown job type {kind!r}"
        unknown = set(job.get("params", {})) - PARAMS[kind]
        assert not unknown, f"{path.name}:{job_id}: undocumented params {unknown}"
        # every needs.<id>.outputs.<x> names a job this one depends on, and an output it has
        text = yaml.safe_dump(job)
        deps = set(job.get("needs", [])) | set(job.get("after", []))
        for ref_job, output in NEEDS_REF.findall(text):
            assert ref_job in deps, f"{path.name}:{job_id}: reads {ref_job} without needs/after"
            ref_kind = jobs[ref_job]["type"]
            assert output in OUTPUTS.get(
                ref_kind, set()
            ), f"{path.name}:{job_id}: {ref_job} ({ref_kind}) has no output {output!r}"


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_environments_match_the_build_profile(path: Path) -> None:
    """A fingerprint hashed (or an update published) in the wrong environment never
    matches the builds it's meant for, and ships the wrong env vars."""
    jobs = _load(path)["jobs"]
    profiles = {
        j["params"]["profile"] for j in jobs.values() if j.get("type") in {"build", "get-build"}
    }
    assert len(profiles) == 1, f"{path.name}: one profile per workflow, got {profiles}"
    want = _profile_env(profiles.pop())
    for job_id, job in jobs.items():
        if job.get("type") in {"fingerprint", "update"}:
            got = job.get("environment", "production")
            assert got == want, f"{path.name}:{job_id}: environment {got!r}, profile uses {want!r}"


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_platforms_are_independent(path: Path) -> None:
    """get-build is per platform, and each OTA depends only on its own platform's
    lookup: an iOS-only native change must not hold back the Android OTA."""
    jobs = _load(path)["jobs"]
    for job_id, job in jobs.items():
        if job.get("type") == "get-build":
            assert job["params"].get("platform") in {"android", "ios"}, f"{path.name}:{job_id}"
        if job.get("type") == "update":
            platform = job.get("params", {}).get("platform")
            assert platform in {"android", "ios"}, f"{path.name}:{job_id}: set params.platform"
            lookups = [n for n in job.get("needs", []) if jobs[n].get("type") == "get-build"]
            assert lookups and all(
                jobs[n]["params"]["platform"] == platform for n in lookups
            ), f"{path.name}:{job_id}: depends on another platform's build lookup"


def test_release_submits_what_it_builds() -> None:
    jobs = _load(WORKFLOWS / "release.yml")["jobs"]
    built = {j["params"]["platform"] for j in jobs.values() if j.get("type") == "build"}
    submits = [j for j in jobs.values() if j.get("type") == "submit"]
    assert len(submits) == len(built) == 2
    assert "production" in _eas().get("submit", {}), "eas.json needs submit.production"


def test_ascappid_is_an_apple_id_when_set() -> None:
    """Provision writes the App Store Connect Apple ID here. It's a number, never a
    bundle id or a placeholder; a wrong value makes every TestFlight submit fail."""
    ios = _eas().get("submit", {}).get("production", {}).get("ios", {})
    if "ascAppId" in ios:
        assert re.fullmatch(r"\d{6,12}", str(ios["ascAppId"])), ios["ascAppId"]
    for key in ("ascApiKeyPath", "serviceAccountKeyPath"):
        for platform in ("ios", "android"):
            path = _eas().get("submit", {}).get("production", {}).get(platform, {}).get(key)
            assert not path, f"{key} points at a key file; keep keys in EAS (`eas credentials`)"


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_every_update_uploads_sentry_source_maps(path: Path) -> None:
    """An OTA bundle replaces the JS the build uploaded maps for, so without its own
    upload every crash in it is minified noise. `true` makes the job FAIL when the
    upload fails; left out, EAS only tries and stays green. An app that chose no Sentry
    (appbox.yaml `stack.errors: none`) says `false` instead, explicitly."""
    want = _errors_stack() == "sentry"
    for job_id, job in _load(path)["jobs"].items():
        if job.get("type") != "update":
            continue
        got = job.get("params", {}).get("upload_sentry_sourcemaps")
        assert got is want, (
            f"{path.name}:{job_id}: set params.upload_sentry_sourcemaps: {str(want).lower()}"
            + (" so OTA crashes are readable in Sentry" if want else " (stack.errors is not sentry)")
        )


def test_production_otas_roll_out_in_stages() -> None:
    """A bad OTA reaches every user on their next launch. Production updates start at a
    slice of users, and reach 100% only through an approval (the crash-free check in
    docs/runbooks/release.md) followed by an update-rollout of that same update group."""
    jobs = _load(WORKFLOWS / "release.yml")["jobs"]
    updates = {k: j for k, j in jobs.items() if j.get("type") == "update"}
    assert updates, "release.yml publishes no OTA"
    for job_id, job in updates.items():
        pct = job.get("params", {}).get("rollout_percentage")
        assert isinstance(pct, int) and 0 < pct < 100, (
            f"release.yml:{job_id}: rollout_percentage {pct!r}; production OTAs start staged (1-99)"
        )
        promotes = [
            j
            for j in jobs.values()
            if j.get("type") == "update-rollout"
            and job_id in j.get("needs", [])
            and f"needs.{job_id}.outputs.first_update_group_id"
            in str(j.get("params", {}).get("update_group_id", ""))
        ]
        assert promotes, f"release.yml:{job_id}: no update-rollout job promotes this update"
        for promote in promotes:
            gates = [
                n
                for n in promote.get("needs", [])
                if jobs[n].get("type") == "require-approval" and job_id in jobs[n].get("needs", [])
            ]
            assert gates, (
                f"release.yml:{job_id}: promoted to {promote.get('params', {}).get('rollout_percentage', 100)}% "
                "with no require-approval after the update (check crash-free sessions first)"
            )


def test_previews_never_stage() -> None:
    """A staged rollout in progress blocks the next update on that runtime, so a staged
    PR preview would fail the PR's next push. Previews go to their branch at 100%."""
    for job_id, job in _load(WORKFLOWS / "pr-preview.yml")["jobs"].items():
        if job.get("type") == "update":
            pct = job.get("params", {}).get("rollout_percentage", 100)
            assert pct == 100, f"pr-preview.yml:{job_id}: rollout_percentage {pct}; previews ship at 100%"
