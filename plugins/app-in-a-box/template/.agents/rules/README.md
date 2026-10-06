# Path rules

Short, imperative rules that apply when you edit files matching `globs:`.

- **Claude Code** injects the matching rule automatically the first time per session
  you edit a matching file (`.claude/hooks/inject-path-rules.py`).
- **Codex / other agents:** the table in the root `AGENTS.md` lists these. Read the
  rule before editing a matching file.

Format:

    ---
    description: one line
    globs: backend/**, mobile/lib/api.ts
    ---
    Rule body (markdown). A `!pattern` in globs excludes.

`optional/` holds domain overlays (health, financial, children's data, location, UGC,
biometric) that the scaffold copies up when `appbox.yaml.product.sensitive_data` names
them. The matching guardrail packs enforce them in code: `docs/privacy/GUARDRAILS.md`.
