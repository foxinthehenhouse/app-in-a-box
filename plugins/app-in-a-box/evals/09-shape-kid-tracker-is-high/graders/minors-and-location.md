---
type: regex
target: {source: file, path: design/brief.json}
flags: s
---
"risk"\s*:\s*\{(?=.*"id"\s*:\s*"minors")(?=.*"id"\s*:\s*"location")
