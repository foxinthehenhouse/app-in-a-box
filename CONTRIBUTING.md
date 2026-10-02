# Contributing

Thanks for helping. App in a Box is a kit whose product is the repo it generates, so
most changes land in `plugins/app-in-a-box/template/` and are proven by the selftest,
which renders that template and runs its guards.

## Setup

- Python 3.12 with PyYAML (`pip install pyyaml`), Node 22, git.
- Optional, for the checks that need them: `actionlint`, `zizmor`, `gitleaks`, the
  Maestro CLI, and Postgres with pgTAP. Locally, a check whose tool is missing prints
  `SKIP`. In CI (`APPBOX_SELFTEST_STRICT=1`) a skip is a failure, so CI runs everything.

## The one rule: prove it can fail

Run the selftest before every PR:

```bash
scripts/selftest.sh            # renders the template, ~200 checks, a few minutes
scripts/selftest.sh --mobile   # adds a real create-expo-app + npm run gates (~5 min)
```

If you add or change a guard, add a check to `scripts/selftest.d/<area>.sh` that
**plants the violation and expects the guard to fail**, next to the check that it
passes. A guard nobody has seen fail reads as protection without giving any. Every
area file shows the pattern (`check` for "passes", `refuses` for "fails on a plant").

## Changing a skill

Skills are graded by evals (`plugins/app-in-a-box/evals/` for the kit,
`template/.agents/evals/` for the generated app's skills). Runs use your own Anthropic
API key and cost about $3–4:

```bash
claude plugin eval plugins/app-in-a-box --ablation none --scaffold \
  --allow-tools Write Edit Bash -j 4 --threshold 0.8
```

Or add an `ANTHROPIC_API_KEY` secret to your fork and run **Actions → Evals** there.
Paste the score table into your PR. Every case must average ≥ 0.8. A new skill gets at
least one case where it should fire and one where it shouldn't.

## Pull requests

- Branch from `main`, one change per PR. PRs are squash-merged.
- Say what changed, why, and how you verified it (the PR template asks).
- The repo is public: no secrets, no links to private repos or trackers. The selftest
  fails on private ticket IDs.
- Changes to the generated app follow its own rules in
  `plugins/app-in-a-box/template/AGENTS.md`: tokens instead of hex, an analytics event
  per screen, additive-only wire changes, a Maestro flow per screen, and so on. The
  template's gates enforce most of them.

## Things only a real account can verify

The selftest covers everything a container can run. A device, EAS builds and store
submission need real accounts, so they're a release checklist anyone can run with
free-tier accounts: [RELEASING.md](RELEASING.md).

