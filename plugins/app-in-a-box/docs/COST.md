# Cost: an afternoon, not a fortune

Setup runs a team of agents. These rules keep it fast and affordable without making
it worse. They come from a token-efficiency study on the app this kit was extracted
from: fixed context was about 13k tokens per session before the first prompt, fan-out
reviewers each re-read the same material, and rework (building the wrong thing) was the real bill.

## The rules

1. **Specs, not markup.** Agents write `design/prototype.json`; `scripts/prototype.py`
   renders the HTML deterministically. A model never writes a 2,000-line HTML file,
   and switching a variant or a palette re-renders for free.
2. **The brief is the context.** `design/brief.json` (below, ≤ ~1.5k tokens) is all the
   helpers get. The conversation stays with `product-advisor`.
3. **Route by job.** Extraction runs on haiku, copy and generation on sonnet, and
   talking and judging on opus (each agent's `model:` sets it). Don't override without
   a reason.
4. **Bounded fan-out.** At most 4 helpers at once. In Codex, run them one after another.
5. **Fix before showing.** One `design-critic` pass before the founder sees anything:
   a critic round costs less than a round trip through a human.
6. **Stable prefix.** Pass `docs/TASTE.md` and `brief.json` first and unchanged to every
   helper, so repeated calls hit the prompt cache.
7. **Maps, not whole files.** When an agent needs to know what's in a big file, give it
   the headings or the symbol list, not the file.
8. **Measure, don't guess.** After phase 6 the generated repo has
   `.claude/hooks/spend_ledger.py`; run `python3 .claude/hooks/spend_ledger.py --days 1`
   to report what setup actually spent, and say it in the closing message.

## Budget per phase (guidance, shown to the founder up front)

| Phase | Agents | Rough size |
|---|---|---|
| 1a Shape | advisor + scribe (+ risk-reviewer when the idea touches a sensitive category) | small: a few conversation rounds |
| 1b Idea check (quick) | market-analyst | small; the deep pass is about 4× that and opt-in |
| 2 Prototype | 4 helpers + critic, then 1–3 refine rounds | the largest phase; each refine round is cheap (spec edits + re-render) |
| 3–8 Build | as before | the same as the kit without this flow |

If the founder wants it cheaper: skip the deep idea check, start the prototype with 2
directions instead of 3, and cap refine rounds at 2. Say which lever you pulled.

## The brief

`design/brief.json`, written by `scribe`, updated each shaping round and by every later
phase that settles a decision. It travels into the generated repo at the same path, so
the app's own skills (`next`, `feature-discovery`, `ship`) read the same ledger:

```json
{
  "app": {"name": "…", "one_liner": "…"},
  "users": [{"who": "…", "moment": "when they reach for it", "pain": "their words"}],
  "context": {"frequency": "daily|weekly|when X happens", "where": "on the bus, at the shop…"},
  "core_loop": {"trigger": "…", "action": "…", "feedback": "…", "return": "…"},
  "payoff": {"first_session": "what they must feel before they leave", "moment": "the one moment worth an authored animation"},
  "social": {"shape": "solo|shared|community|two_sided", "cold_start": "how it's useful before anyone else joins"},
  "distribution": {"first_100": "how the first 100 users find it", "channels": ["share", "invite", "referral", "web", "aso"]},
  "money": {"model": "free|subscription|one_off|ads|b2b"},
  "v1_features": ["…"], "maybe_features": ["…"], "out_of_scope": ["…"],
  "feel": {"words": ["…"], "inspiration": ["…"], "avoid": ["…"]},
  "constraints": {"platforms": ["ios", "android"], "accounts": "email_otp", "sensitive": []},
  "validation": {"verdict": "…", "angle": "…", "riskiest": ["…"]},
  "risk": {"tier": "standard|elevated|high|stop", "categories": [], "questions": [],
           "abuse_cases": [], "accepted": [], "screened_at": "shape", "declined": []},
  "decisions": [
    {"id": "platforms", "question": "Which phones?", "answer": "iPhone and Android",
     "status": "default", "ask_at": "shape", "why": "sets the build profiles and store accounts"},
    {"id": "pricing", "question": "What does it cost, and where's the paywall?", "answer": null,
     "status": "deferred", "ask_at": "pre-launch", "why": "price is cheap to change and best set once people use it"}
  ],
  "open_questions": ["…"]
}
```

**The decision ledger** (`decisions`) is how the kit asks only what's expensive to
change on day 0 and leaves the rest for the moment it matters. Every product call the
team makes or parks gets one entry:

- `status`: `asked` (the founder answered), `default` (the team assumed it and said so:
  "I'm assuming…, say if not"), or `deferred` (not decided yet; `answer` is `null`).
- `ask_at`: when it gets settled: `shape`, `prototype`, `scaffold`, `first-feature`,
  `pre-launch` or `post-launch`. The phase that owns it asks it and flips the entry to
  `asked` or `default`. In the generated repo, `next` surfaces a `deferred` decision
  whose phase has arrived.
- `why`: one line on what the answer changes, shown with the question.

**The risk block** (`risk`) is the risk screen's record (`skills/shape` → "The risk
screen"; categories in `scripts/risk/categories.json`): the tier, each sensitive
category and why, the must-answer questions (each also in `decisions`), the abuse
cases, the owner's acknowledgments at tier high, and anything declined.
`scripts/risk_screen.py render` turns it into `docs/product/RISK.md`.

`money.model` is the model only. The price and the paywall's placement are a
`pre-launch` decision. `python3 "$KIT/scripts/check_intake.py" brief design/brief.json`
validates the shape (the ledger, the five day-0 sections and the `risk` block are
required), checks the risk block against the keyword backstop, and caps the questions
asked at shape at 7.
