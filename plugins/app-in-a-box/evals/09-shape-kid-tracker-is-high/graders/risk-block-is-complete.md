---
type: llm
focus: {source: file, path: design/brief.json}
weight: 3
---
The brief's `risk` block, for a map where parents see their children's check-ins:
1. Records the consent question (who agrees for the child, and whether the child can see
   who sees them) and the visibility question (who sees a location, live or last
   check-in) as asked or stated defaults, with answers that match the user's (a parent
   sets up the profile; the child sees who can see them; last check-in only).
2. Has an abuse case whose actor is a non-custodial parent (or an estranged parent or
   relative kept away by a court), with a concrete mitigation in the design (for example:
   only the guardian who set up the profile adds viewers, and every viewer is listed to
   the child).
3. Records the owner's acknowledgment for both `minors` and `location` in `accepted`
   (by owner, with a date).
4. Every deferred risk question also appears in `decisions` with a later `ask_at`.
