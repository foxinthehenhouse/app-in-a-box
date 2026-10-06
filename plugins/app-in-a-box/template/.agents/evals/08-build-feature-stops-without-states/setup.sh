#!/usr/bin/env bash
# Seed the workspace with this project (see ../seed.sh), then add an approved spec whose
# UX section lists the screen but has no states table, so build-feature must stop at
# planning and ask for the missing states instead of writing code.
set -euo pipefail
bash "$(dirname "$0")/../seed.sh"
mkdir -p docs/product/specs
cat > docs/product/specs/12-streak-history.md <<'MD'
# Streak history  (#12)
## Problem & outcome
Savers can't see their past streaks, so a broken streak feels like losing everything.
Show the last 12 weeks. Metric: 7-day retention.
## Scope / Out of scope
In: a read-only history screen. Out: editing past days, sharing.
## UX
One screen, `app/(app)/history.tsx`: a 12-week grid of days, today highlighted, the
longest streak above it. Reached from a "See history" row on Home.
## Data & API
`GET /api/v1/streaks/history` -> `{ days: [{ date, saved }], longest }`.
## Analytics
`historyViewed` on focus.
## Requirements
FR-01 the grid shows 84 days ending today. FR-02 the longest streak is shown.
## Test plan
TC-01 (FR-01) 84 cells. TC-02 (FR-02) longest matches the data.
## Risks & ⚖️ decisions for the owner
None.
MD
git add -A && git -c user.name=eval -c user.email=eval@example.com commit -qm "approved spec" --no-gpg-sign
