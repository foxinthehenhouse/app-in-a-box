# Postmortem: <one line: what users saw>

Copy to `docs/postmortems/YYYY-MM-DD-<slug>.md` once the incident is over (the
`incident` skill drafts it). Blameless: name the gap in the system, never a person.
`tests/test_postmortems.py` fails CI on a postmortem whose "Guard added" section
doesn't link a guard that exists, because a write-up without a guard is how the same
incident happens twice.

- **Date:** YYYY-MM-DD
- **Severity:** SEV1 | SEV2 | SEV3 (`docs/runbooks/incident.md`)
- **Detected by:** <Sentry alert, /health, a user report, the north-star report...>
- **Time to detect / mitigate / fix:** <minutes> / <minutes> / <hours>
- **Release:** <API sha, OTA update group, build number>

## What happened

<Two or three sentences a user would recognise.>

## Timeline

| Time (UTC) | Event |
|---|---|
| hh:mm | <the bad change shipped> |
| hh:mm | <first signal> |
| hh:mm | <mitigated: rollback / kill switch> |
| hh:mm | <fixed> |

## Impact

<Who, how many, for how long. Data exposed or lost? (SEV1: see the runbook's notice rules.)>

## Root cause

<The change, and why nothing caught it before users did.>

## Mitigation

<What stopped the bleeding: the rollback, the kill switch, the hotfix. How long it took.>

## Guard added

<The test, check or alert that now fails on this exact failure, as a backticked repo
path (`tests/test_x.py::test_name`, `scripts/check_x.py`, a jest test), plus the
planted violation it was proven against. It must exist when this file merges.>

## Follow-ups

- [ ] <ticket link>: <what, owner>
