# Test fixtures (not examples)

Files here exist only so the kit's selftests have something to check. They are not
sample apps, they don't ship to users, and nothing in the plugin reads them.

- `sample/tokens.json`: an alternate design direction for the contrast and
  light/dark checks (`selftest.d/polish.sh`).
- `sample/VALIDATION.md`: an idea-check report that follows the report contract
  (`selftest.d/validate.sh`).
- `prototype.json`: a prototype spec for the renderer's render/check/freeze checks
  (`selftest.d/prototype.sh`). A neutral placeholder app, not a product example.
- `risk-brief.json`: a complete tier-high brief (a neutral placeholder: parents see a
  child's check-ins) for the risk screen's brief, backstop and RISK.md checks
  (`selftest.d/risk-screen.sh`).
