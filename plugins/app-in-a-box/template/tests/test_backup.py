"""Nightly backups never print a secret, and only ever upload ciphertext.

.github/workflows/backup.yml runs scripts/backup-db.sh with the database URL (it holds
the password) and the bucket's keys in its environment. A backup log that shows one of
them is a leak on every run, and GitHub's log masking only covers the exact secret
string, not the password inside the URL. Two layers, each with a negative control:

  - static: no secret reaches a `run:` block except through `env:`, the script never
    echoes a secret variable or turns on xtrace, and nothing in the workflow can decrypt
    (the private key never goes to GitHub);
  - behaviour: the real script runs with planted secrets and fake CLIs, and its output
    must not contain them, even when a CLI fails and echoes the URL back.

The real round trip (real age, a real Postgres, restore-drill.sh) is in the kit's
selftest; this file runs in the app's CI without either.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "backup.yml"
SCRIPT = ROOT / "scripts" / "backup-db.sh"

# Always secret, whatever the workflow maps them from. The rest come from the workflow:
# every env var whose value is a `${{ secrets.* }}`.
ALWAYS_SECRET = ("SUPABASE_DB_URL", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID")
PRINTS = re.compile(r"\b(echo|printf|cat|tee|logger)\b|>&2|\bset\s+-[a-z]*x|xtrace|\bbash\s+-x")
XTRACE = re.compile(r"^\s*set\s+-[a-z]*x|set\s+-o\s+xtrace|\bbash\s+-[a-z]*x\b", re.M)
DECRYPT = re.compile(
    r"AGE-SECRET-KEY|AGE_IDENTITY|BACKUP_AGE_KEY\b|\bage\b[^\n]*\s(-d|--decrypt|-i)\b"
)


def _steps(doc: dict) -> list[dict]:
    return [s for job in (doc.get("jobs") or {}).values() for s in job.get("steps") or []]


def secret_names(doc: dict) -> set[str]:
    names: set[str] = set(ALWAYS_SECRET)
    for st in _steps(doc):
        for k, v in (st.get("env") or {}).items():
            if "secrets." in str(v):
                names.add(k)
    return names


def _prints_secret(line: str, names: set[str]) -> bool:
    return bool(PRINTS.search(line)) and any(re.search(rf"\${{?{n}\b", line) for n in names)


def _workflow_leaks(doc: dict, workflow_raw: str, names: set[str]) -> list[str]:
    problems: list[str] = []
    for st in _steps(doc):
        run = str(st.get("run", ""))
        if "secrets." in run:
            problems.append(
                f"backup.yml: a `run:` block expands a secret inline; pass it through `env:`: {run.strip()[:80]}"
            )
        problems += [
            f"backup.yml: a step prints a secret: {line.strip()}"
            for line in run.splitlines()
            if _prints_secret(line, names)
        ]
    if DECRYPT.search(workflow_raw):
        problems.append(
            "backup.yml: references a decryption key; GitHub gets the PUBLIC key only (BACKUP_AGE_RECIPIENT)"
        )
    return problems


def _script_leaks(script: str, names: set[str]) -> list[str]:
    problems: list[str] = []
    if XTRACE.search(script):
        problems.append(
            "backup-db.sh: turns on xtrace, which prints every command with its secret values"
        )
    problems += [
        f"backup-db.sh:{i}: prints a secret: {line.strip()}"
        for i, line in enumerate(script.splitlines(), 1)
        if not line.lstrip().startswith("#") and _prints_secret(line, names)
    ]
    if not re.search(r"age_cli\[@\]\}?\"?\s+\"\$\{recipients\[@\]\}\"", script):
        problems.append(
            "backup-db.sh: doesn't encrypt with age to BACKUP_AGE_RECIPIENT before upload"
        )
    if re.search(r"--decrypt|\s-d\s+-i\b", script):
        problems.append("backup-db.sh: decrypts; the backup side holds the public key only")
    return problems


def leaks(workflow_raw: str, script: str) -> list[str]:
    """Every way the backup could print a secret or read a backup, as messages."""
    doc = yaml.safe_load(workflow_raw)
    names = secret_names(doc)
    return _workflow_leaks(doc, workflow_raw, names) + _script_leaks(script, names)


def test_backup_never_prints_a_secret_or_holds_a_private_key() -> None:
    problems = leaks(WORKFLOW.read_text(), SCRIPT.read_text())
    assert not problems, "\n".join(problems)


def test_backup_workflow_is_nightly_gated_and_runs_the_script() -> None:
    doc = yaml.safe_load(WORKFLOW.read_text())
    on = doc.get("on", doc.get(True))
    assert on["schedule"]
    assert "workflow_dispatch" in on
    job = doc["jobs"]["backup"]
    assert "vars.BACKUP_AGE_RECIPIENT" in job["if"], "off until provision sets the recipient"
    assert any(s.get("run", "").strip() == "scripts/backup-db.sh" for s in job["steps"])
    assert os.access(SCRIPT, os.X_OK)
    assert os.access(ROOT / "scripts" / "restore-drill.sh", os.X_OK)


# ---- negative controls: each static rule must be able to fail -------------------

_ECHO = 'echo "connecting to $SUPABASE_DB_URL"\n'


@pytest.mark.parametrize(
    ("plant", "needle"),
    [
        (lambda w, s: (w, s + _ECHO), "backup-db.sh:"),
        (lambda w, s: (w, s.replace("set -euo pipefail", "set -euxo pipefail")), "xtrace"),
        (lambda w, s: (w, s + 'printf "%s" "${AWS_SECRET_ACCESS_KEY}" >&2\n'), "prints a secret"),
        (
            lambda w, s: (
                w.replace("run: scripts/backup-db.sh", 'run: echo "$SUPABASE_DB_URL"'),
                s,
            ),
            "backup.yml: a step prints a secret",
        ),
        (
            lambda w, s: (
                w.replace(
                    "run: scripts/backup-db.sh",
                    "run: scripts/backup-db.sh ${{ secrets.SUPABASE_DB_URL }}",
                ),
                s,
            ),
            "expands a secret inline",
        ),
        (
            lambda w, s: (
                w.replace(
                    "          BACKUP_AGE_RECIPIENT:",
                    "          AGE_IDENTITY: ${{ secrets.BACKUP_AGE_IDENTITY }}\n          BACKUP_AGE_RECIPIENT:",
                ),
                s,
            ),
            "references a decryption key",
        ),
        (
            lambda w, s: (
                w.replace(
                    "          BACKUP_S3_BUCKET:",
                    "          NEW_TOKEN: ${{ secrets.NEW_TOKEN }}\n          BACKUP_S3_BUCKET:",
                ),
                s + 'echo "token $NEW_TOKEN"\n',
            ),
            'prints a secret: echo "token $NEW_TOKEN"',
        ),
        (lambda w, s: (w, s.replace('"${recipients[@]}"', "--armor")), "doesn't encrypt with age"),
    ],
)
def test_leak_lint_catches(plant, needle: str) -> None:
    w, s = plant(WORKFLOW.read_text(), SCRIPT.read_text())
    problems = leaks(w, s)
    assert any(needle in p for p in problems), problems


# ---- behaviour: the real script, planted secrets, fake CLIs ----------------------

DB_PW = "pw-planted-7d1e9a0c"
DB_URL = f"postgresql://postgres.abcdefghijklmnop:{DB_PW}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
# Planted values are joined at run time, so neither this file nor its .pyc holds a
# key-shaped literal for the repo's own gitleaks scan to flag.
S3_KEY = "-".join(["s3", "secret", "planted", "55aa11ff"])
S3_ID = "s3-id-planted-0042"
RECIPIENT = "age1" + "q" * 58

FAKES = {
    # supabase db dump --db-url URL -f FILE [--role-only | --use-copy --data-only]
    "supabase": r"""#!/usr/bin/env bash
out="" kind=schema
while [ $# -gt 0 ]; do case "$1" in -f) out="$2"; shift 2 ;; --role-only) kind=roles; shift ;;
  --data-only) kind=data; shift ;; --db-url) url="$2"; shift 2 ;; *) shift ;; esac; done
if [ -n "${FAKE_SUPABASE_FAIL:-}" ]; then echo "failed to connect to $url: password authentication failed" >&2; exit 1; fi
case "$kind" in
  roles) echo "-- roles" > "$out" ;;
  data) echo "COPY public.notes (id) FROM stdin;" > "$out" ;;
  *) [ -n "${FAKE_EMPTY_SCHEMA:-}" ] && : > "$out" || echo "CREATE TABLE public.notes (id int);" > "$out" ;;
esac
""",
    # age -r R... -o OUT IN: a stand-in "ciphertext" (base64), unless told to misbehave
    "age": r"""#!/usr/bin/env bash
while [ $# -gt 2 ]; do case "$1" in -o) out="$2"; shift 2 ;; *) shift ;; esac; done
in="$1"
if [ -n "${FAKE_AGE_PLAINTEXT:-}" ]; then cp "$in" "$out"; exit 0; fi
{ echo "age-encryption.org/v1"; base64 < "$in"; } > "$out"
""",
    # aws s3 cp SRC s3://bucket/key [...]: copies into $FAKE_S3, logs argv
    "aws": r"""#!/usr/bin/env bash
echo "$*" >> "$FAKE_S3/argv.log"
dest="${4#s3://}"; mkdir -p "$FAKE_S3/$(dirname "$dest")"; cp "$3" "$FAKE_S3/$dest"
""",
}


def _run(tmp_path: Path, *args: str, **extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir, s3 = tmp_path / "bin", tmp_path / "s3"
    bin_dir.mkdir(exist_ok=True)
    s3.mkdir(exist_ok=True)
    for name, body in FAKES.items():
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_S3": str(s3),
        "SUPABASE_DB_URL": DB_URL,
        "BACKUP_AGE_RECIPIENT": RECIPIENT,
        "BACKUP_S3_BUCKET": "penny-backups",
        "BACKUP_S3_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
        "AWS_ACCESS_KEY_ID": S3_ID,
        "AWS_SECRET_ACCESS_KEY": S3_KEY,
        **extra,
    }
    env = {k: v for k, v in env.items() if v != "<unset>"}
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60
    )
    return proc, s3


def _assert_no_secret(text: str) -> None:
    for s in (DB_URL, DB_PW, S3_KEY, S3_ID):
        assert s not in text, f"the backup printed a secret ({s[:6]}...)"


def test_backup_uploads_ciphertext_and_prints_no_secret(tmp_path: Path) -> None:
    proc, s3 = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    _assert_no_secret(proc.stdout + proc.stderr)
    objs = sorted((s3 / "penny-backups" / "db").glob("db-*.tar.age"))
    assert len(objs) == 1, list(s3.rglob("*"))
    assert objs[0].read_bytes().startswith(b"age-encryption.org/v1")
    argv = (s3 / "argv.log").read_text()
    assert "--endpoint-url https://acct.r2.cloudflarestorage.com" in argv
    _assert_no_secret(argv)  # the aws CLI reads its keys from the environment, not argv
    assert "uploaded s3://penny-backups/db/" in proc.stdout


def test_a_failing_dump_that_echoes_the_url_is_scrubbed(tmp_path: Path) -> None:
    proc, _ = _run(tmp_path, FAKE_SUPABASE_FAIL="1")
    assert proc.returncode == 1
    assert "dumping roles failed" in proc.stderr
    assert "***" in proc.stderr
    _assert_no_secret(proc.stdout + proc.stderr)


def test_refuses_plaintext_an_empty_schema_and_a_private_key(tmp_path: Path) -> None:
    proc, s3 = _run(tmp_path, FAKE_AGE_PLAINTEXT="1")
    assert proc.returncode == 1
    assert "isn't age output; refusing to upload" in proc.stderr
    assert not (s3 / "penny-backups").exists()

    proc, _ = _run(tmp_path, FAKE_EMPTY_SCHEMA="1")
    assert proc.returncode == 1
    assert "no CREATE TABLE" in proc.stderr

    # Joined at run time too: a `+` of literals is constant-folded into the .pyc.
    private = "-".join(["AGE", "SECRET", "KEY", "1" + "Q" * 58])
    proc, _ = _run(tmp_path, BACKUP_AGE_RECIPIENT=private)
    assert proc.returncode == 2
    assert "PRIVATE key" in proc.stderr
    assert private not in proc.stdout + proc.stderr


def test_missing_config_is_named(tmp_path: Path) -> None:
    proc, _ = _run(tmp_path, SUPABASE_DB_URL="<unset>", AWS_SECRET_ACCESS_KEY="<unset>")
    assert proc.returncode == 2
    assert "SUPABASE_DB_URL" in proc.stderr
    assert "AWS_SECRET_ACCESS_KEY" in proc.stderr


def test_out_mode_writes_locally_and_needs_no_bucket(tmp_path: Path) -> None:
    out = tmp_path / "local"
    proc, s3 = _run(
        tmp_path, "--out", str(out), BACKUP_S3_BUCKET="<unset>", AWS_SECRET_ACCESS_KEY="<unset>"
    )
    assert proc.returncode == 0, proc.stderr
    assert len(list(out.glob("db-*.tar.age"))) == 1
    assert not (s3 / "argv.log").exists()
    _assert_no_secret(proc.stdout + proc.stderr)
