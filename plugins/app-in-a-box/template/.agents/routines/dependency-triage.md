# dependency-triage

Cadence: weekly (Mon 08:xx). Runs in: cloud. Connectors: none (gh + the repo).

1. Open dependency PRs: `gh pr list --search "author:app/dependabot author:app/renovate" --json number,title,headRefName,statusCheckRollup`.
   For each: CI green and a patch/minor bump → recommend merge; red or a major bump →
   read its changelog and say what would break. Don't merge anything.
2. Known vulnerabilities: `cd mobile && npm audit --omit=dev --json` and
   `pipx run pip-audit -r requirements.txt` (or `python -m pip_audit` if installed).
   Keep only high/critical, or anything reachable from code we ship.
3. One issue, `dependency-triage: <date>`: a table of PR → recommendation → why, then
   vulnerabilities → package → fixed-in version → the PR or command that fixes it.
   Nothing to report → no issue.
