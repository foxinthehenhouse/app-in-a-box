---
type: llm
focus: trace
weight: 2
---
The ticket the agent filed (or, if `gh` failed for lack of auth, the exact ticket it
prepared) has:
1. An imperative, specific title about the resend button (e.g. "Fix OTP resend on Android").
2. A body with a Problem section and an Acceptance criteria checklist (`- [ ]`) that
   includes a visible error or confirmation for the user.
3. A type label `fix` and a priority label (`p0`–`p2`).
The agent does not start fixing the code, and does not keep the ticket only in chat
or a scratch file without attempting to file it.
