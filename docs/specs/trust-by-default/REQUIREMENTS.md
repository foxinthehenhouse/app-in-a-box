# Trust by default: privacy, safety, security and compliance (shared contract)

**Ask (owner, 2026-10-06):** every app the kit builds should be secure, and the idea itself
should uphold privacy, security, compliance and ethics. Catch risky ideas early (example: a
map that lets parents track children), and build the guardrails in from the first commit so
they never become a long-term problem. Enforce it in development through skills, hooks and
linters, not prose.

This file is the contract four parallel workstreams share. Each owns its files; read the
others' sections so the formats line up. Commit this file into the repo as
`docs/specs/trust-by-default/REQUIREMENTS.md` (the risk-screen workstream does; the others
reference that path).

## Principles

1. **Screen the idea, not just the code.** Shape classifies the idea against sensitive
   categories before anything is built. The agent's judgment classifies; a deterministic
   keyword backstop catches what it missed (an idea mentioning "kids" and "location" can
   never come out "standard").
2. **Ask only what changes the architecture.** Each category has 1-3 must-answer questions
   (who consents, who can see what, how long it's kept). Everything else is a default
   guardrail, stated, not asked.
3. **Misuse is a first-class user.** Every elevated idea gets a short abuse case: who could
   use this to harm whom (an abusive partner, a non-custodial parent, a stalker), and what
   in the design stops it.
4. **Guardrails are code.** A category turns on a guardrail pack that lints, tests and
   defaults enforce, each with a planted negative control (the kit's one rule).
5. **Flag and guard; refuse only the narrow harmful core.** ⚖️ Default taken (owner may
   overrule): the kit builds elevated and high-risk ideas with guardrails and an explicit,
   recorded owner acknowledgment; it declines only designs whose core is covert or
   non-consensual (tracking or monitoring an adult without their knowledge, hidden
   monitoring apps, de-anonymising people, content sexualising minors) and offers the
   consented version instead. Alternative: hard-block every high-tier idea until a human
   review.
6. **Not legal advice.** RISK.md and the checklists say which regimes may apply and why, and
   recommend counsel at tier high. They never claim compliance.

## Categories (ids are the contract)

`minors`, `location`, `health`, `biometric`, `financial`, `ugc` (user-generated content and
messaging between users), `intimate` (dating, sexual health, sexuality), `surveillance`
(monitoring another person), `ai_decisions` (automated decisions about people), `regulated`
(gambling, crypto, medical device, legal or financial advice).

Tiers: `standard` < `elevated` < `high` < `stop`. Each category has a `tier_floor`; the idea's
tier is the max over its categories, raised one step for risky combinations (`minors` +
`location`, `minors` + `ugc`, `surveillance` + anything, `health` + `ai_decisions`).

Kit data file (owned by the risk-screen workstream):
`plugins/app-in-a-box/scripts/risk/categories.json`, one entry per category:
`{id, title, tier_floor, triggers: [keywords], questions: [{id, text, why}],
guardrails: [pack ids], regimes: [{name, applies_when, link}], stop_patterns: [text],
abuse_prompts: [text]}`.

## design/brief.json `risk` block (owned by the risk-screen workstream)

```json
"risk": {
  "tier": "high",
  "categories": [{"id": "minors", "why": "tracks children's location", "source": "inferred"}],
  "questions": [{"id": "location.consent", "category": "location", "status": "asked", "answer": "..."}],
  "abuse_cases": [{"actor": "non-custodial parent", "harm": "locates the child against a court order", "mitigation": "..."}],
  "accepted": [{"item": "location.background", "by": "owner", "on": "2026-10-06", "note": "..."}],
  "screened_at": "shape",
  "declined": []
}
```
`check_intake.py` validates it. The ledger (`decisions`) carries any deferred risk question
with its `ask_at` like every other decision.

## docs/product/RISK.md (generated, prose kept outside markers)

Sections: Summary (tier, categories, one line each), Who could be harmed and how (abuse
cases), Guardrails built in (each pack, what it enforces, where), Open questions (with
`ask_at`), Accepted risks (who, when, why), Regimes that may apply (with links), Not legal
advice. Generated blocks are fenced by markers, as DESIGN.md does.

## Generated app: privacy data map (owned by the data-map workstream)

`privacy/data-map.yaml` in the template:
```yaml
packs: [location, minors]          # set from design/brief.json risk.categories at scaffold
tables:
  profiles:
    owner: user                    # user | org | system
    columns:
      display_name: {category: identifier, purpose: "shown to the user", retention: account}
analytics:
  screen_viewed: {props: {screen: none}}
permissions:
  location_when_in_use: "show the child's last check-in to their parent"
```
Column categories: `none`, `identifier`, `contact`, `location`, `health`, `financial`,
`biometric`, `ugc`, `minor`, `usage`, `device`. Retention: `account` (deleted with the
account) or an ISO-8601 duration. A guard fails when a migration column, an analytics prop
or an Expo permission is missing from the map, and when a sensitive category lacks a
retention or is sent to analytics. The map generates the App Store privacy answers and
`PrivacyInfo.xcprivacy` entries, the Play data-safety answers, and a privacy-policy draft.

## Generated app: guardrail packs (owned by the guardrails workstream)

Pack ids (match `guardrails` in categories.json): `baseline` (always on), `location`,
`minors`, `health`, `ugc`, `financial`, `biometric`. Enabled packs are read from
`privacy/data-map.yaml` → `packs` (fall back to `baseline` alone if the file is absent).
Each pack is lints, tests, defaults and docs; each guard has a planted negative control.

## Kit: pre-launch gate (owned by the launch-gate workstream)

`ship` refuses while RISK.md has open questions or a high-tier category lacks an accepted
or resolved item; `next` surfaces them; a per-category compliance checklist (store
guidelines, age rating, regimes) is generated for the owner; adding a feature that touches
a new category re-runs the screen.

## As built: the risk screen (formats the other workstreams read)

- **Script:** `plugins/app-in-a-box/scripts/risk_screen.py` (`screen`, `check`, `render`,
  `packs`). `check_intake.py brief` runs the same `validate()`, so there is one set of
  rules for the `risk` block.
- **categories.json extras** beyond the per-category contract: each question also has
  `theme` (age, consent, visibility, purpose, retention, safety) and `ask_at`. Shape asks
  only `ask_at: shape` questions, grouped by theme so one question can settle several
  categories; the rest go in the ledger with their phase. Top-level `vocab` (words a
  trigger's `{name}` expands to), `packs` (what each guardrail pack guards, for RISK.md),
  `combinations`, `stop_rules` (each with the `reframe` to offer, or `null` when there is
  no consented version), `derive` (for example a partner's location implies
  `surveillance`), `sensitive_map` (`constraints.sensitive` -> category) and `social_map`
  (`community`/`two_sided` -> `ugc`). `baseline` is implied, not listed per category.
- **Tier rules:** the highest floor, raised one step when a combination is present
  (`minors`+`location`, `minors`+`ugc`, `minors`+`intimate`, `surveillance`+anything,
  `health`+`ai_decisions`, `intimate`+`location`), capped at `high`: only a stop rule
  reaches `stop`. A brief whose tier is `stop` fails `check_intake`; after the covert core
  is declined, the brief describes the consented version and records `risk.declined`
  (`item`, `why`, `reframe`).
- **Categories needing the owner's acknowledgment** at tier high: every category with
  floor `high`, plus every member of a combination that applies. Each needs a
  `risk.accepted` entry with `by: "owner"` and `item` equal to the category id or
  `<category>.<question>`. `risk_screen.py screen` prints them as `needs_ack`.
- **Risk questions in the ledger:** every `risk.questions` entry has a `decisions` entry
  with the same id, or names it in `decision` (one decision can cover several risk
  questions, which keeps the 7-question cap honest). A question whose catalogue `ask_at`
  is `shape` can't be deferred: ask it or state a default.
- **RISK.md** (`docs/product/RISK.md`): generated blocks fenced as
  `<!-- risk.md:generated:<key> -->` ... `<!-- /risk.md:generated:<key> -->`, keys
  `summary`, `abuse`, `guardrails`, `open`, `accepted`, `regimes`, `legal`. The `open`
  block lists each deferred risk question as ``- `<id>` (<category>, ask at <phase>): <text>``
  and says `None open.` when there are none. `render --check` exits 1 on drift.
- **Packs for the data map:** `risk_screen.py packs design/brief.json` prints the packs
  the brief's categories turn on, `baseline` first, one per line.
