---
type: regex
target: {source: file, path: appbox.yaml}
match: not_contains
flags: i
---
(sk-[a-z0-9]{10,}|password\s*:|secret_key\s*:\s*\S{8,}|api_key\s*:\s*\S{8,})
