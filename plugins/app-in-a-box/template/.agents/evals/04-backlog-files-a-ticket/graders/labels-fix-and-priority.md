---
type: regex
target: last_message
flags: i
---
(--label|labels?)[^\n]{0,40}\bfix\b[^\n]{0,20}\bp[0-2]\b|(--label|labels?)[^\n]{0,40}\bp[0-2]\b[^\n]{0,20}\bfix\b
