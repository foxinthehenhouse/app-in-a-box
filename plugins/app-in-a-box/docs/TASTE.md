# Taste: what "beautiful and intuitive" means here

The whole team designs against this page, and `design-critic` scores every prototype
against it before a founder sees it. The mechanical parts are also lints in
`scripts/prototype.py check`, so they can't be argued away.

## Product

1. **The first five minutes are the product.** A new user reaches the core loop in one
   tap and feels its payoff in the first session. Onboarding that delays that is a cost.
2. **Every screen has one job.** If you describe a screen's purpose with "and", split it.
3. **One primary action per screen, under the thumb.** Everything else is secondary,
   ghost or tucked away, and the primary is never an optional feature. *(lint)*
4. **Outcomes, not features.** Name things by what the user gets ("See your week"),
   not by the mechanism ("Analytics").
5. **Honest states.** Loading shows shape (a skeleton), empty says what to do next,
   errors say what happened and offer a way forward. Never fake data. *(lint: every
   list has an empty state)*
6. **Scope is a design tool.** v1 is the core loop done beautifully. Optional features
   stay as toggles until someone can say what they'd measure.
7. **The screenshot test.** Is there a moment a user would screenshot and send to a
   friend? If no screen earns that, the payoff isn't visible enough.

## Visual

1. **Restraint beats decoration.** One accent colour, used for the thing you want
   tapped. Neutrals tinted toward the brand hue, never dead grey.
2. **Hierarchy by size and weight first, colour last.** A screen should read correctly
   in greyscale.
3. **Rhythm.** Spacing from the token scale only; related things close, groups apart.
   Density is a choice (the prototype's slider), not an accident.
4. **Type does the work.** Two families at most; numbers in a face that makes them
   feel important when they are.
5. **Motion has a job**: confirm a tap, show where something went, celebrate the
   payoff. Nothing moves just to move, and reduce-motion is always honoured.
6. **Both modes are designed**, not inverted. Dark surfaces get lighter as they rise.
7. **Contrast is not negotiable.** The ink ramp clears 4.5:1 on every surface, in both
   modes. *(lint: `check_contrast.py`)*

## Copy

Buttons are verbs. Empty states are one helpful line. The users' words, not the
founder's internal names. Warm and competent; no guilt, no hype, no jargon. Real
sample content from their domain, never lorem. *(lint: no lorem, TODO or xxx)*

## Three diagnostics (run them on every key screen)

- **Squint:** blur your eyes. You should see one clear focal point and a calm
  structure, not a barcode of equal-weight rows.
- **Delete the icons:** remove every icon mentally. If the screen stops making sense,
  the words and layout are doing too little.
- **Screenshot:** would anyone share this? What exactly would they be showing off?

## Anti-slop list (fail on sight)

- A gradient wash behind grey cards; glassmorphism for its own sake.
- Emoji as UI (icons, bullets, section headers).
- Generic hero art or stock illustration standing in for the product.
- Lorem ipsum, "Item 1/2/3", "John Doe".
- More than one accent competing; every button the same weight.
- Centred-everything layouts; walls of equal cards.
- A ghost or outline button as the primary action.
- Tiny tap targets (under 48px) or grey-on-grey text.
- Onboarding carousels before the user has done anything.
- More than five tabs.

## Where this comes from

Distilled from the source app's craft canon: its atmosphere diagnostics, a 22-app UX benchmark
with an "options ladder", and its product leads' heuristics. The lesson that shaped
this whole kit: "vanilla" is usually a **layout** failure, not a palette failure, so
the prototype lets founders compare layouts, not just colours.
