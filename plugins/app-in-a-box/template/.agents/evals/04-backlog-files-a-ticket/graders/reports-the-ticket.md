---
type: llm
weight: 3
---
1. The final message says what was filed: an issue number or link, or, if filing
   wasn't possible here (no `gh`, no auth, no remote), the exact ticket it prepared
   and the command to file it.
2. The title is imperative and specific to the resend-code button.
3. The ticket body has a Problem section and an Acceptance criteria checklist
   (`- [ ]`) that includes a visible error or confirmation for the user.
4. The agent does not start fixing the code.
