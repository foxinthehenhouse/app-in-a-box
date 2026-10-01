# .agents: the agent-neutral harness

Source of truth for every coding agent working in this repo (Claude Code, Codex, and
anything else that reads `AGENTS.md` or the Agent Skills format).

| What | Source of truth | Claude Code | Codex |
|---|---|---|---|
| Project instructions | `AGENTS.md` (+ nested) | `CLAUDE.md` → `@AGENTS.md` | reads `AGENTS.md` |
| Skills | `.agents/skills/*/SKILL.md` | `.claude/skills` (symlink), `/name` | native, `$name` |
| Subagents | `.agents/agents/*.md` | `.claude/agents` (symlink) | `.codex/agents/*.toml` (generated) |
| Path rules | `.agents/rules/*.md` | auto-injected by hook | read per the table below |
| Memory | `.agents/memory/` | recall hook + index | read `MEMORY.md` at session start |
| MCP servers | `.mcp.json` | native | `.codex/config.toml` (generated) |
| Hooks | `.claude/hooks/*` scripts | `.claude/settings.json` | `.codex/hooks.json` (trust once) |
| Hard guards | `.githooks/` (no commits on main, no secrets, gates on push) | both | both |

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
