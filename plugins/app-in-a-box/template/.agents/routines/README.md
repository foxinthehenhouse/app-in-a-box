# Routines

One file per scheduled ritual. A Routine's prompt points at its file, so the prompt
stays one line and the procedure lives (and is reviewed) in the repo. The `routines`
skill offers these, one yes each, and records what's scheduled in
`.claude/harness/manifest.json` → `cadence.scheduled`. The selftest checks every
menu row has a file and every skill a file names exists.

Every run: never merge, never push to main, never file a ticket the procedure says
needs approval; put proposals in ONE issue titled `<routine>: <date>`.
