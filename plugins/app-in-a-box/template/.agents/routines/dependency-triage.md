# dependency-triage

Cadence: weekly (Mon 08:xx). Runs in: cloud. Connectors: none (gh + the repo).

1. Open dependency PRs: `gh pr list --search "author:app/dependabot author:app/renovate" --json number,title,headRefName,statusCheckRollup`.
   For each: CI green and a patch/minor bump → recommend merge; red or a major bump →
   read its changelog and say what would break. Don't merge anything.
2. Known vulnerabilities: `python3 scripts/check_npm_audit.py` (npm, high/critical,
   minus what `mobile/npm-audit-allowlist.json` has triaged; expired entries show up
   here first) and `scripts/dev-venv.sh pip-audit --disable-pip --require-hashes -r
   requirements-dev.lock`. Keep only high/critical, or anything reachable from code we ship.
   A Dependabot pip PR that is red on `check_lock.py` needs `scripts/lock-deps.sh` run on
   its branch; say so in the table.
3. One issue, `dependency-triage: <date>`: a table of PR → recommendation → why, then
   vulnerabilities → package → fixed-in version → the PR or command that fixes it.
   Nothing to report → no issue.
