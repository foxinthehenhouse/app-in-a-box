# Taste: what "beautiful and intuitive" means here

The whole team designs against this page, and `design-critic` scores every prototype
against it (and against screenshots of it) before a founder sees it. The mechanical
parts are lints, so they can't be argued away: `prototype.py check` in the kit, and in
the app `check_design.py` (tokens) and `check-design-tells.js` (code) in `npm run gates`.

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
   list has an empty state; in the app, every data screen renders all three)*
6. **Scope is a design tool.** v1 is the core loop done beautifully. Optional features
   stay as toggles until someone can say what they'd measure.
7. **The screenshot test.** Is there a moment a user would screenshot and send to a
   friend? If no screen earns that, the payoff isn't visible enough.

## Visual

1. **Restraint beats decoration.** One accent colour, used for the thing you want
   tapped, with a hue from the product's meaning (never the stock AI violet). Neutrals
   tinted toward the brand hue, never dead grey. *(lint)*
2. **Hierarchy by size and weight first, colour last.** A screen should read correctly
   in greyscale.
3. **Rhythm.** Spacing from the token scale only; related things close, groups apart.
   Density is a choice (the prototype's slider), not an accident.
4. **Type does the work.** Two families at most; numbers in a face that makes them
   feel important when they are. Pick the face from the product's world, never the one
   every generator reaches for: Inter, Open Sans, Lato, Montserrat, Fraunces, Geist,
   Space Grotesk, Instrument, Plus Jakarta, Mona Sans, Recoleta, Arial, Helvetica, or
   Roboto as a loaded font. The phone's own system font is always fine. *(lint)*
   Headings balance their lines; display tracking stops at -0.04em (-0.02 to -0.03 reads
   better); body copy sits at 45–75 characters a line and scales with Dynamic Type.
5. **Motion has a job**: confirm a tap, show where something went, celebrate the
   payoff. Nothing moves just to move, and reduce-motion is always honoured. (The
   Motion section below has the numbers.)
6. **Both modes are designed**, not inverted. Dark surfaces get lighter as they rise.
7. **Contrast is not negotiable.** The ink ramp clears 4.5:1 on every surface, in both
   modes, including the lit ground behind the content and glass over it. *(lint:
   `check_contrast.py`; the prototype composites its atmosphere and checks that too)*
8. **Depth is light, not lines.** Shadows have an offset and a soft blur; a zero-blur
   offset shadow is a costume. Declare elevation once: a hairline border *or* a soft
   shadow, not both. Glass and blur are a specific effect (bars, sheets, a chosen
   atmosphere), never the default surface.

## Motion

Timing follows distance and consequence:

| Duration | Use |
|---|---|
| 100–150ms | immediate feedback: a press, a toggle |
| 150–300ms | a routine state change: a chip, a segment, a row expanding |
| 300–500ms | a screen, a sheet, an overlay |
| 500–800ms | one authored moment, at most one per flow |

- **Exit faster than you enter.** Arrivals decelerate (`cubic-bezier(0.16, 1, 0.3, 1)`
  or a critically damped spring); exits accelerate away.
- **Content and screens never bounce.** Overshoot belongs to small things a finger
  moved (a press releasing, a chip, a thumb), on springs, and to the payoff
  `Celebration`. A bounce or elastic curve on an entrance reads dated. *(lint: easing
  curves in tokens.json, `Easing.bounce/elastic/back` and overshooting beziers in code)*
- **One authored moment, not scattered effects.** The prototype gives you the house
  choreography for free (overlapping blur-rise screen changes, staggered content, touch
  bloom, a receding sheet). Spend your one moment on the core loop's payoff.
- **Stagger a list as a list**, capped (55ms a step, eight steps at most). Never
  stagger every section of a screen.
- **Reduced motion is a designed path**, not "off": crossfades instead of slides,
  the atmosphere holds still, numbers show their final value. Feedback that confirms an
  action stays.

## Platform (iOS and Android)

The app follows each platform's own grammar; the brand speaks through tint, type,
motion and content. The tell is "ported from a website" (or an iPhone app wearing
Android's skin).

- **Navigation is the system's:** a tab bar (2–5 sections, never actions), a stack for
  hierarchy, a sheet for a self-contained task. Edge-swipe back (iOS) and system Back
  (Android) always work. The kit's `NativeTabs`, Stack and `formSheet` routes do this.
- **Native controls first:** switches, segmented controls, pickers, action sheets, swipe
  actions, snackbars. Reinventing them for flavour is the most common native tell.
- **Safe areas and insets:** nothing under the Dynamic Island, notch, home indicator or
  system bars; the keyboard never hides the field being typed into.
- **Touch targets:** 44pt (iOS) and 48dp (Android) minimum; the kit uses 48 for both.
- **Type scales with the user:** Dynamic Type / font scale, from the token type roles,
  never a hard-coded size. Body is 16–17pt; nothing below 11pt.
- **Icons are drawn:** SF Symbols on iOS, Material Symbols on Android (`Icon`), one
  weight. Never an emoji or a text glyph standing in for one. *(lint)*
- **Check it on the real thing:** screenshots from the simulator or emulator in both
  appearances and at a large text size, not just a browser. Say which produced the
  evidence.

## Copy

Buttons are verbs. Empty states are one helpful line. The users' words, not the
founder's internal names. Warm and competent; no guilt, no hype, no jargon. Real
sample content from their domain, never lorem. *(lint: no lorem, TODO or xxx)*

In the app, `check-copy.js` holds every string in `locales/` to these *(lint)*:

- **No filler or blame:** never "Oops", "Whoops", "Error occurred", "Please note" or
  "Invalid" (say what a good value looks like). Never "Click": people tap, so name the
  action. "Something went wrong" only with a next step after it.
- **Errors say what happened and what to do.** An error string (a key with `error` or
  `failed` in its path) gives a reason ("couldn't reach the server") or a next step
  ("Check your connection and try again"), ideally both.
- **No shouting:** no ALL CAPS word over three letters, except real acronyms (JSON,
  GDPR). No "!!" anywhere, and no "!" in an error: a failure isn't exciting.
- A deliberate exception (the word DELETE a user must type) goes in the locale's
  `_copyIgnore` map with its reason.

## Three diagnostics (run them on every key screen)

- **Squint:** blur your eyes. You should see one clear focal point and a calm
  structure, not a barcode of equal-weight rows.
- **Delete the icons:** remove every icon mentally. If the screen stops making sense,
  the words and layout are doing too little.
- **Screenshot:** would anyone share this? What exactly would they be showing off?

## Anti-slop list (fail on sight)

This list grows. When `design-critic` (or a founder) spots a new generic tell, add it
here in one line, and if a regex or a token rule can catch it, add the lint too.

- A gradient wash behind grey cards; glassmorphism for its own sake.
- Gradient text. Emphasis comes from weight or size. *(lint)*
- A small eyebrow label over every heading; numbered section markers (01 / 02 / 03).
  *(lint: at most one eyebrow per screen)*
- The hero-metric template: a big number, a small label, three supporting stats, an
  accent. Show the thing the number is about.
- Cards inside cards. Cards are the lazy container; use rows, spacing and dividers.
  *(lint)*
- A coloured stripe down one side of a card, callout or row. *(lint)*
- Hard offset shadows (`4px 4px 0`) outside a world that is genuinely neo-brutal.
  *(lint)*
- Monospace as a costume for "technical", rather than for numbers and data.
- Bounce or elastic easing on anything that isn't a small, touched element. *(lint)*
- Emoji as UI (icons, bullets, section headers). *(lint)*
- Generic hero art or stock illustration standing in for the product.
- Lorem ipsum, "Item 1/2/3", "John Doe".
- More than one accent competing; every button the same weight.
- The overused fonts, pure-grey neutrals, the stock AI violet (Visual 1 and 4). *(lint)*
- Light or dark picked by category ("fitness is dark") instead of from where and when
  the app is used.
- Centred-everything layouts; walls of equal cards. *(lint: four cards in a row)*
- A ghost or outline button as the primary action.
- Tiny tap targets (under 48px) or grey-on-grey text.
- Onboarding carousels before the user has done anything.
- More than five tabs.

## Where this comes from

Distilled from the source app's craft canon: its atmosphere diagnostics, a 22-app UX benchmark
with an "options ladder", and its product leads' heuristics. The lesson that shaped
this whole kit: "vanilla" is usually a **layout** failure, not a palette failure, so
the prototype lets founders compare layouts, not just colours.

The craft floor, motion timing, anti-pattern list and the platform section adapt
material from [Impeccable](https://github.com/pbakaus/impeccable) by Paul Bakaus
(Apache License 2.0), rewritten for a React Native app and its prototype. Impeccable's
iOS and Android references are themselves distilled from ehmo's
[platform-design-skills](https://github.com/ehmo/platform-design-skills) (MIT). Changes:
condensed, merged with this kit's rules, and turned into this kit's own checks where a
rule is mechanical. Licence texts and notices: `THIRD_PARTY_NOTICES.md` in the App in a
Box repository.
