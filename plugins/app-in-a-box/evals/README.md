# App in a Box kit evals

Checks that the kit's own skills behave: `new-app` gets to the interview and asks
real product questions, `interview` writes a correct `appbox.yaml` + brief, the
scaffold never overwrites a hand-edited brief, and none of it fires on an unrelated
question. Format: `claude plugin eval` case folders (`prompt.md` + `graders/*.md`).

From the kit repo root:

```bash
claude plugin eval plugins/app-in-a-box --ablation with-without --no-publish --allow-tools Write "Bash(python3:*)"
```

`03-scaffold-keeps-brief` runs the renderer, so it needs the `--allow-tools` grant
above; without it that case scores 0 in both arms. The headline number is Δ (with
plugin − without). A Δ that falls after a skill edit means the edit made it worse.

The generated app has its own suite in `template/.agents/evals/`.
