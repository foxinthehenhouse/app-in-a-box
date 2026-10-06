---
type: regex
target: last_message
flags: i
---
states?\b[^\n]{0,200}\b(loading|empty|error|offline)\b|\b(loading|empty|error|offline)\b[^\n]{0,200}\bstates?\b
