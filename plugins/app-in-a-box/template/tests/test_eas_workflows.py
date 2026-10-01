"""EAS Workflows + eas.json, checked against the documented job schema.

EAS runs these files on Expo's servers, so a mistake only shows when a release
silently does the wrong thing: a PR preview that publishes with production env
vars, a fingerprint that never matches a build, or an iOS submit that dies for
lack of `ascAppId`. The rules come from the EAS Workflows docs source
(expo/expo docs/pages/eas/workflows/pre-packaged-jobs.mdx).
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
