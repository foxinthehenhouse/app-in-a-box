# __APP_NAME__

__ONE_LINER__

<!-- Built with App in a Box: to remove the badge, delete the next line. Nothing else depends on it. -->
[![Built with App in a Box](https://img.shields.io/badge/built%20with-App%20in%20a%20Box-2f7a67)](https://github.com/foxinthehenhouse/app-in-a-box)

An Expo (iOS and Android) app with a FastAPI backend on Supabase. The product brief is
`docs/product/BRIEF.md`; the setup record (stack, resources, progress) is `appbox.yaml`.

## Run it

```bash
scripts/dev-venv.sh python -m pytest -q     # backend tests
./run.sh                                     # API on :8000 with reload
cd mobile && npm run gates                   # tsc + eslint + guard scripts + jest
cd mobile && npx expo start                  # app in Expo Go / dev client
cd mobile && npm run demo                    # the whole app with no accounts
```

## Where to look

- [AGENTS.md](AGENTS.md): the project's rules, commands and a map of screens, APIs
  and tables. Claude Code and Codex both read it.
- [docs/runbooks/release.md](docs/runbooks/release.md): how a change reaches users,
  and [rollback.md](docs/runbooks/rollback.md) for when it shouldn't have.
- [docs/decision-log.md](docs/decision-log.md): architectural decisions, append-only.

This README is yours: re-rendering the template never overwrites it.
