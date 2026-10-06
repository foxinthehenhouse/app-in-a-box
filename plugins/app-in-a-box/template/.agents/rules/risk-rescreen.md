---
description: A screen or spec that touches a new risk category re-runs the idea's risk screen
globs: docs/product/SCREENS.md, docs/product/specs/**
---
The idea was screened for risk at shape (`design/brief.json` → `risk`, readable in
docs/product/RISK.md). A new screen or feature can carry it into a category it was
never screened for: a map, a chat, a kids mode, a health log.

- **After editing this file, re-screen it:**
  `python3 scripts/risk_gate.py rescreen --file <this file>`. A new category is added to
  the brief with its must-answer questions opened and the tier raised.
- **Ask before building.** Put the opened questions to the owner in one structured round
  (recommended answer first), write each answer back to `risk.questions`, add a misuse
  case (who could use this to harm whom, and what stops it), and regenerate RISK.md.
- **A false match** (the "map" is a list of shops, no one's location) is the owner's
  call: record it in `risk.accepted` with the category id, `by`, `on` and a note.
- `ship` runs `python3 scripts/risk_gate.py check`, which scans these files too and
  refuses while anything is open. Never edit the brief to make it pass.
