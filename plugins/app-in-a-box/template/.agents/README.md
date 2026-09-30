# .agents: the agent-neutral harness

Source of truth for every coding agent working in this repo (Claude Code, Codex, and
anything else that reads `AGENTS.md` or the Agent Skills format).

- `skills/`: Agent Skills (`SKILL.md` with `name` + `description` frontmatter). Codex
  reads this folder natively; Claude Code reads it through the `.claude/skills`
  symlink.
- `agents/`: subagent roles in markdown. Claude uses them via `.claude/agents`;
  Codex gets generated `.codex/agents/*.toml`.
- `rules/`: path-scoped rules (see `rules/README.md`).
- `memory/`: long-term memory notes + `MEMORY.md` index.
- `evals/`: skill evals (`claude plugin eval .agents`); `.claude-plugin/plugin.json`
  exists only so the eval runner can load this folder's skills as a plugin.
- Generated inside skills: `<skill>/agents/openai.yaml` (Codex policy for
  explicit-only skills). Don't edit; the renderer rewrites it.

After adding or editing an agent role, or changing `.mcp.json` or
`.claude/settings.json` hooks, regenerate the Codex adapters:

```
python3 <app-in-a-box plugin>/scripts/render.py --adapters-only --target .
```

On a system without symlink support (Windows without developer mode), the renderer
copies `skills/` and `agents/` into `.claude/` instead. Re-run it after edits.
