# App in a Box kit evals

Checks that the kit's own skills behave:
- `new-app` opens as Rae: it plays a seeded idea back and asks product gaps, or invites a ramble when there's no idea yet.
- `shape` writes `design/brief.json`, `appbox.yaml` and the brief.
- `prototype` runs the check before rendering and fixes what it flags.
- `scaffold` never overwrites a hand-edited brief.
- None of it fires on an unrelated question.

Each case folder holds `prompt.md`, `graders/*.md` and, when it needs a seeded repo, a `case.yaml` scaffold.

From the kit repo root:

```bash
claude plugin eval plugins/app-in-a-box --ablation with-without --no-publish \
  --scaffold --allow-tools Write Edit Bash
```

- `--allow-tools ... Bash` is needed because the scaffold and prototype cases run the kit's scripts. Runs are OS-sandboxed. A narrower grant such as `Bash(python3:*)` denies compound commands like `mkdir -p x && ...`, and after one denial the agent stops trying, so those cases score 0.
- `--scaffold` runs the template suite's `setup.sh` scripts, which seed the workspace with a rendered app (`template/.agents/evals/seed.sh`). We wrote them; only pass `--scaffold` for cases you trust.
- The eval sandbox masks `.claude/*` in the workspace root, so any case that renders the template renders into a subfolder (`app/`).

The headline number is Δ (with plugin − without). A Δ that falls after a skill edit means the edit made it worse.

The generated app has its own suite in `template/.agents/evals/`.
