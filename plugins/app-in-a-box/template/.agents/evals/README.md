# Skill evals

Do the project's skills fire when they should, stay quiet when they shouldn't, and
produce what they promise? Each folder is one case: `prompt.md` (frontmatter + the
prompt) and `graders/*.md` (one check each).

```bash
claude plugin eval .agents --ablation with-without --no-publish
```

`--ablation with-without` runs every case with and without these skills. The number
that matters is **Δ**, the with-skills score minus the without-skills score. A skill
whose Δ is ≤ 0 costs context and buys nothing, and `harness-optimize` treats it as a
pruning or rewrite candidate. Results land in `.agents/evals/results/<timestamp>/`.

Rules for new cases:
- Grade outcomes (what the answer contains), not just which tool ran. A `tool_used:
  Skill` grader is display-only under ablation.
- Keep at least one should-NOT-fire case per skill you add.
- Cases run in an empty sandbox folder, not this repo, so put any code the skill
  needs to see (a diff, a spec) in the prompt itself.
- Give each case the tools its graders need (`allowed_tools`). A missing tool scores
  0 in both arms and reads as "the skill did nothing".

Codex has no eval runner. The cases are plain markdown, so you can read a prompt, run
it in Codex, and grade by hand when a Codex-only change needs checking.
