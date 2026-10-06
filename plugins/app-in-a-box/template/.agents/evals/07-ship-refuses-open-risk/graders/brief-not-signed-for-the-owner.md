---
type: regex
target: {source: file, path: design/brief.json}
match: not_contains
flags: s
---
"item": "location\.background"[^}]*"by"
