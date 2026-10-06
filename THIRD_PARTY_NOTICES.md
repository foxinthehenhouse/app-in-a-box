# Third-party notices

App in a Box is MIT licensed (`LICENSE`). It adapts material from the projects below,
used under their licences. The full licence texts are in `licenses/`.

## Impeccable

- **Project:** https://github.com/pbakaus/impeccable (Paul Bakaus)
- **Licence:** Apache License 2.0 (`licenses/Apache-2.0-impeccable.txt`)
- **Version used:** commit `e103efe` (October 2026), detector engine `v0.1.11`
- **What we use, and how it was changed:**
  - `plugins/app-in-a-box/docs/TASTE.md` (and the copy every generated app gets as
    `docs/design/TASTE.md`): the craft floor, motion timing, anti-pattern list and the
    platform section adapt Impeccable's `craft-floor.md`, `animate.md`, `typeset.md`,
    `colorize.md`, `ios.md` and `android.md`. They are condensed, rewritten for a React
    Native app and its prototype, and merged with this kit's own rules.
  - `template/scripts/check_design.py` and `template/mobile/scripts/check-design-tells.js`
    reimplement some of Impeccable's detector rules (overused fonts, bounce easing,
    nested cards, side-stripe borders, hard offset shadows, gradient text, glyph icons)
    as our own code for tokens and React Native. No Impeccable code is copied; the
    overused-font list mirrors its `OVERUSED_FONTS` constant.
  - Kit CI (`.github/workflows/kit.yml`, job `design`) downloads the pinned Impeccable
    detector binary, verifies its checksum and runs it against the rendered prototype.
    It is never installed into, or downloaded by, a generated app.

Impeccable's own notice, which applies to the platform material above:

> The `skill/reference/ios.md` and `skill/reference/android.md` platform reference
> files are distilled from ehmo's `platform-design-skills` (Apple Human Interface
> Guidelines and Material Design 3 rules), rewritten in Impeccable's voice.

## platform-design-skills

- **Project:** https://github.com/ehmo/platform-design-skills (ehmo)
- **Licence:** MIT (`licenses/MIT-platform-design-skills.txt`)
- **What we use:** indirectly, through Impeccable's iOS and Android references (the
  "Platform" section of `TASTE.md`).

## DESIGN.md format (Google Stitch)

- **Project:** https://github.com/google-labs-code/design.md (Google LLC)
- **Licence:** Apache License 2.0 (`licenses/Apache-2.0-design-md.txt`)
- **Version used:** format version `alpha`, commit `9bf8eae` (July 2026)
- **What we use, and how it was changed:**
  - `plugins/app-in-a-box/template/scripts/design_md.py` writes every generated app's
    `DESIGN.md` in this format: the frontmatter schema (`version`, `name`,
    `description`, `colors`, `typography`, `rounded`, `spacing`, `components`) and the
    eight body sections in the spec's order. It is our own code, projecting
    `design/tokens.json`; no Stitch code is copied. We add sections the format leaves
    out (Dark Mode, Motion, Atmosphere, Iconography, Agent Prompt Guide, Decisions),
    which the spec tells consumers to preserve, and marker comments that let the file
    be regenerated without losing hand-written prose.
