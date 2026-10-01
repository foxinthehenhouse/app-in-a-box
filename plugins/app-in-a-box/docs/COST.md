# Cost: an afternoon, not a fortune

Setup runs a team of agents. These rules keep it fast and affordable without making
it worse. They come from Forge's token-efficiency study: fixed context was about 13k
tokens per session before the first prompt, fan-out reviewers each re-read the same
material, and rework (building the wrong thing) was the real bill.

## The rules

1. **Specs, not markup.** Agents write `design/prototype.json`; `scripts/prototype.py`
   renders the HTML deterministically. A model never writes a 2,000-line HTML file,
   and switching a variant or a palette re-renders for free.
2. **The brief is the context.** `design/brief.json` (below, ≤ ~1.5k tokens) is all the
   helpers get. The conversation stays with `product-advisor`.
3. **Route by job.** Extraction and copy run on haiku, generation on sonnet, and
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
| 1a Shape | advisor + scribe | small: a few conversation rounds |
| 1b Idea check (quick) | market-analyst | small; the deep pass is about 4× that and opt-in |
| 2 Prototype | 4 helpers + critic, then 1–3 refine rounds | the largest phase; each refine round is cheap (spec edits + re-render) |
| 3–8 Build | as before | the same as the kit without this flow |

If the founder wants it cheaper: skip the deep idea check, start the prototype with 2
directions instead of 3, and cap refine rounds at 2. Say which lever you pulled.

## The brief

`design/brief.json`, written by `scribe`, updated each shaping round:

```json
{
  "app": {"name": "…", "one_liner": "…"},
  "users": [{"who": "…", "moment": "when they reach for it", "pain": "their words"}],
  "core_loop": {"trigger": "…", "action": "…", "feedback": "…", "return": "…"},
  "v1_features": ["…"], "maybe_features": ["…"], "out_of_scope": ["…"],
  "feel": {"words": ["…"], "inspiration": ["…"], "avoid": ["…"]},
  "constraints": {"platforms": ["ios", "android"], "accounts": "email_otp", "sensitive": []},
  "validation": {"verdict": "…", "angle": "…", "riskiest": ["…"]},
  "open_questions": ["…"]
}
```
