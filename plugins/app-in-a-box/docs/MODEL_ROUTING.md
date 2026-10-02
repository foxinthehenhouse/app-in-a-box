# Model routing: which model each role runs on

Every subagent role in the generated repo (`.agents/agents/*.md`) declares a
`model` and an `effort` in its frontmatter. The rule of thumb: spend the expensive
model where a wrong answer is expensive, and the cheap one where the work is sorting.

| Tier | Claude Code value | Used for | Roles |
|---|---|---|---|
| Fable 5.1 | `model: fable`, `effort: high` | Final ruling on calls that are expensive to reverse (risky merges, migrations, locked specs). One call per decision, never for volume. | `chair` |
| Opus 5.5 | `model: opus` | Orchestration, judgement, review verdicts, specs | `correctness-reviewer` (high), `lead-engineer` (high), `product-manager` (medium) |
| Sonnet 5 | `model: sonnet`, `effort: medium` | Building and focused review | `mobile-engineer`, `qa-engineer`, `ux-designer`, `growth`, `design-a11y-reviewer` |
| Haiku 4.5 | `model: haiku`, `effort: low` | Cheap sweeps: CI-log and lint triage, dependency PRs, capture summaries, signal gathering for `next` | `triage` |

The values are Claude Code's model aliases (`opus`, `sonnet`, `haiku`, `fable`), so
they follow Anthropic's current model in each family without edits. `effort` accepts
`low`, `medium`, `high`, `max`. The main session keeps whatever model the owner
launched with; only subagents are routed.

## Codex mapping

The renderer (`scripts/render.py`, `codex_agent_toml`) turns each role into
`.codex/agents/<name>.toml`. Codex role files accept `model` and
`model_reasoning_effort` (checked against the Codex source, `agent/role.rs`):

| Claude frontmatter | Codex TOML | Notes |
|---|---|---|
| `effort: low / medium / high` | `model_reasoning_effort = "low" / "medium" / "high"` | same scale |
| `effort: max` | `model_reasoning_effort = "xhigh"` | not every Codex model has `max`; `xhigh` works on all current ones |
| `model: opus` etc. | *(omitted: inherits the session model)* + a `# Claude tier:` comment | Codex model slugs change often, and a pinned slug that stops existing breaks the role |
| `codex_model: <slug>` (optional) | `model = "<slug>"` | pin a Codex model for one role on purpose |
| `tools:` | *(no equivalent)* | Codex role files have no per-role tool list; read-only roles say "read-only" in their instructions |

Skills: Claude's `disable-model-invocation: true` becomes a generated
`<skill>/agents/openai.yaml` with `policy.allow_implicit_invocation: false`, so
explicit-only skills (`ship`, `routines`) stay explicit in Codex too.

## ⚖️ Defaults that are the owner's call

- **Opus-heavy vs Sonnet-heavy.** The default routes judgement roles (correctness
  review, lead engineer, PM) to Opus and building roles to Sonnet. The cheaper alternative
  is Sonnet everywhere except `correctness-reviewer` and `chair`, which roughly
  halves subagent spend at some cost to spec and review quality. Change the
  `model:` lines; `harness-optimize` proposes downgrades when the spend ledger shows
  a role costing more than it returns.
- **Copy on Sonnet, not Haiku.** ⚖️ Kyle 2026-10-02: Sonnet over Haiku for copy. The
  kit's `agents/copywriter.md` runs `model: sonnet` (effort low): every string a user
  reads is written once and shipped, so the cheaper tier's savings weren't worth its
  misses. Extraction (`scribe`) stays on Haiku.
- **Codex inherits rather than pins.** The alternative is a tier table
  (e.g. haiku → the fast Codex model) pinned in the renderer, which saves money in
  Codex but breaks whenever OpenAI retires a slug. Pin per role with `codex_model:`
  if you want it.
