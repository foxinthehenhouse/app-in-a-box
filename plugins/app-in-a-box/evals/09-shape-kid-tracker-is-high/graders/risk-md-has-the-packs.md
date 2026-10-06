---
type: regex
target: {source: file, path: docs/product/RISK.md}
flags: s
---
risk\.md:generated:guardrails(?=.*\(`minors`\))(?=.*\(`location`\)).*?/risk\.md:generated:guardrails
