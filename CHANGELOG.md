# Changelog

All notable changes to App in a Box. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the kit uses
[semantic versioning](https://semver.org/) (pre-1.0, so a minor version can change
how setup works). The version lives in both plugin manifests; the selftest checks
they agree with this file and the README.

## [0.7.0] - 2026-10-04

The first release from this public repository.

### Added

- **A prototype that looks finished on the first render** (#13): an atmosphere lit
  from each direction's accent with every ink kept at AA on the lit ground, motion
  on the spring tokens (overlapping screen changes, staggered content, press bloom,
  springy sheets), device realism (Dynamic Island, metal frame, glass tab bar),
  inlined Latin font subsets, and panel knobs for light, intensity, glass and grain.
  Every effect has a reduced-motion version.
- **Design checks you can't argue with** (#14): the taste rubric adopts Impeccable's
  craft floor, motion timing, anti-patterns and iOS/Android platform rules (with
  attribution in `THIRD_PARTY_NOTICES.md`). `check_design.py` rejects overused fonts,
  pure-grey neutrals, the stock AI violet and overshooting easing in tokens;
  `check-design-tells.js` runs in the generated app's gates; a kit CI `design` job
  runs Impeccable's detector on the rendered prototype. The critic now reviews
  screenshots, and new tells go into the app's `design/avoid.md`.
- **`land`** (#3): a generated-repo skill that drives a PR through review, fixes, CI
  and merge, asking the owner before any merge they haven't pre-approved.
- **Routines as files** (#4): one spec per ritual in `.agents/routines/`, so a
  scheduled run and a hand run read the same instructions. gitleaks in the kit's CI.
- **Skill evals** (#5): every case at 0.8 or above, with an evals workflow you run on
  your own API key.
- **EAS workflows checked against Expo's docs source** (#6): PR previews, release
  (OTA or build and submit, per platform), an OTA rollback script, and the App Store
  Connect and Play submit setup.
- **Maestro** (#7): a flow per screen, a coverage lint in the app's gates, the Maestro
  MCP for both agents, and E2E smoke flows on EAS for every PR.
- **Component tests** (#8): behaviour tests for the component library, haptics graded
  by commitment, a coverage floor, and a lint that every module has a test.
- **Contributor docs** (#9): `CONTRIBUTING.md`, the real-cloud checklist in
  `RELEASING.md`, issue forms and a PR template. `SECURITY.md` for private
  vulnerability reports (#12).
- **Discoverability**: one positioning across the manifests and the README, broader
  keywords, `llms.txt`, six task guides in `docs/guides/`, `SHOWCASE.md` with a
  "Show your app" issue form, maintainer settings in `docs/MAINTAINERS.md`, and a
  small, removable "Built with App in a Box" badge in the generated README. A
  selftest area proves each of these fails when it drifts.

### Changed

- The kit's CI tells the truth (#2): a check that can't run prints `SKIP` locally and
  fails in CI, and the plugin job fails if the `claude` CLI can't start.
- Public-repo hygiene (#9): no private links, ticket IDs or owner secrets anywhere,
  guarded by the selftest.
- The generated README is protected like the brief and tokens: re-rendering with
  `--force` keeps your copy.

### Fixed

- A full teardown review (#11) across the harness, backend and database, mobile,
  CI and selftest, docs and instructions, with a fix and a negative control for every
  finding. Highlights: `service_role` keys caught under any variable name, compiled
  artefacts untracked and guarded, and a failing selftest check prints the lines that
  explain it.
- PR previews ran in the `production` EAS environment, and an iOS-only native change
  left Android without its OTA update (#6).

## [0.6.0] - 2026-10-01

Released before the kit moved to this repository; its history was imported.

### Added

- Shape-first onboarding: a product advisor turns a ramble into a brief, asking only
  what's missing, while a cited idea check runs in the background.
- The clickable prototype: every v1 screen, with switchable design directions,
  layouts, density, motion, copy tone and features, frozen into `design/tokens.json`
  and `docs/product/SCREENS.md` with native iOS and Android symbol mapping.
- Opt-in services, so the stack only provisions what you chose, and a living
  `AGENTS.md` map that a test keeps in step with the code.

[0.7.0]: https://github.com/foxinthehenhouse/app-in-a-box/releases/tag/v0.7.0
