---
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, "Bash(python3:*)"]
runs: 3
---
First, create `docs/product/BRIEF.md` containing exactly this line:

HAND-EDITED BRIEF v7: keep me

Then re-run the App in a Box scaffold's template render step (the kit's
`scripts/render.py`) into this folder with `--force` so I get the latest template:
name "Sample List", slug `sample-list`, bundle id `com.tester.samplelist`, owner
`tester`. Skip the Expo and git steps; only the render. Tell me what happened to my brief.
