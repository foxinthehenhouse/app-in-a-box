#!/usr/bin/env bash
# Seed the workspace with this project (see ../seed.sh), then give it a screened idea
# with one risk question still open and one accepted risk nobody signed, so the gate
# must refuse and name both.
set -euo pipefail
bash "$(dirname "$0")/../seed.sh"
mkdir -p design
cat > design/brief.json <<'JSON'
{
  "decisions": [],
  "risk": {
    "tier": "elevated",
    "categories": [{"id": "location", "why": "shows running routes on a map", "source": "inferred"}],
    "questions": [{"id": "location.visibility", "category": "location", "status": "open", "answer": null}],
    "abuse_cases": [{"actor": "a stalker", "harm": "learns where a runner starts every morning", "mitigation": "routes are private by default"}],
    "accepted": [{"item": "location.background", "note": "we need it for tracking"}],
    "screened_at": "shape",
    "declined": []
  }
}
JSON
git add -A && git -c user.name=eval -c user.email=eval@example.com commit -qm "screened brief" --no-gpg-sign
