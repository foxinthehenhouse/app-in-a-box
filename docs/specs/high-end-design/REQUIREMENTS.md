# High-end design by default: requirements

**Ask (owner, 2026-10-04):** the first HTML a founder sees, the clickable prototype, should
be beautiful and elegant on the first shot, at the level of the best hand-built prototypes
(reference: a recent hand-built "first run" prototype with a lit, animated atmosphere, palettes,
real device chrome and a reduced-motion path). It should not be static or basic. Design
should stay consistent from prototype to the shipped React Native app. Use what the strongest
current models do well for motion and frontend, and it must work equally for Claude and for
OpenAI models through Codex.

## Requirements

1. **First-shot quality.** `prototype.py render` produces a prototype with atmosphere, depth,
   considered type and choreographed motion by default, with no hand-editing. Quality comes
   from the renderer and component library (deterministic), not from hoping a model writes
   good CSS.
2. **Per-app, never templated.** Atmosphere, palette, type and motion temperature derive from
   the app's chosen design direction tokens, so two apps don't look alike.
3. **Consistency, prototype → app.** The same tokens (colour, type, motion curves and
   durations, atmosphere) drive the prototype and the generated Expo app. What the founder
   approves is what ships.
4. **Model-neutral.** Every instruction lives in agent-neutral skills/docs (`.agents/`,
   `AGENTS.md`) that Claude and Codex both read. Nothing depends on one vendor's model,
   tool or API. Model-specific tuning, if any, is optional routing, never required.
5. **A gate, not a hope.** A deterministic check fails the build on generic AI-design tells
   (overused fonts, untinted greys, nested cards, purple gradients, bounce easing, missing
   reduced-motion) in the prototype, and its rules have negative controls in the selftest.
6. **Accessible and fast.** Every motion has a reduced-motion path. Contrast stays gated.
   The prototype stays one self-contained file with a size budget, and atmosphere degrades
   gracefully without WebGL.
7. **Open source safe.** Third-party guidance is used under its licence (attribution and
   NOTICE where required). Generated repos don't need a network download at runtime.

## Decisions (owner, 2026-10-04)

- **Impeccable:** adopt and port. Its craft guidance is adapted into our taste guide with
  Apache-2.0 attribution (plus MIT attribution for the platform references it derives from).
  Its rule ideas become our own checks, which also cover the React Native app. Its detector
  runs in the kit's own CI against the rendered prototype. Generated repos never install it,
  so there are no runtime downloads or telemetry.
- **Atmosphere:** a CSS glow and grain layer by default, and a WebGL "field" each direction can
  opt into, falling back to the glow. **Plus knobs**: the prototype panel lets the founder
  turn design elements on, off and up/down (atmosphere mode and intensity, grain, glass vs
  solid surfaces, field). Knob values freeze into the tokens like every other choice.
- **Fonts:** inline Latin subsets in the prototype, so it renders right offline and forwarded.
- **Rollout:** three PRs. (1) Prototype renderer upgrade. (2) Guidance, impeccable adoption,
  checks and the screenshot-critique step. (3) The same motion and atmosphere tokens in the
  generated Expo app.
