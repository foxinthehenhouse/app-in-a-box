#!/usr/bin/env python3
"""The risk screen: classify an idea against sensitive categories, check the brief's
`risk` block against a deterministic backstop, and render docs/product/RISK.md.

    risk_screen.py screen --idea "a map so parents can see where their kids are"
    risk_screen.py screen --brief design/brief.json
    risk_screen.py check design/brief.json
    risk_screen.py render design/brief.json [--out docs/product/RISK.md] [--check]
    risk_screen.py packs design/brief.json
    risk_screen.py lint [scripts/risk/categories.json]

`screen` prints JSON: the tier, the categories the keywords found (and why), the stop
rules that fired with the consented version to offer, the guardrail packs, the
questions to ask now (grouped by theme, so one question can settle several) and the
ones to defer, the abuse prompts and the regimes that may apply. The agent's judgment
classifies; this is the floor under it: an idea that mentions children and where they
are can never come out "standard".

`check` validates design/brief.json -> risk (check_intake.py brief runs the same code):
the shape, every category's must-answer questions in the ledger, an abuse case for
every elevated idea, the owner's acknowledgment for every high-tier category, and a
tier and category list no lower than the backstop's. One line per problem, exit 1.

`render` writes RISK.md. Only the text between risk.md:generated markers belongs to
this script; your prose outside them survives every run. `--check` exits 1 when a
generated block no longer matches the brief.

`lint` checks categories.json itself: the contract's category and pack ids, 1-3
questions per category each with a phase and a why, and every regime linked to an
official source (the domains in `official_domains`).

`packs` prints the guardrail packs the brief's categories turn on, one per line
(`baseline` first): what the app's privacy/data-map.yaml -> packs starts from.

Data: scripts/risk/categories.json. Not legal advice. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent / "risk" / "categories.json"
TIERS = ("standard", "elevated", "high", "stop")
STATUSES = ("asked", "default", "deferred")
PHASES = (
    "shape",
    "prototype",
    "scaffold",
    "first-feature",
    "pre-launch",
    "post-launch",
)
SOURCES = ("inferred", "backstop", "owner")
ABUSE_KEYS = ("actor", "harm", "mitigation")
ACCEPT_KEYS = ("item", "by", "on", "note")
# The parts of the brief that describe the idea. Decisions, validation and the risk
# block itself are left out: they quote the screen's own words back.
IDEA_KEYS = (
    "app",
    "users",
    "context",
    "core_loop",
    "payoff",
    "v1_features",
    "maybe_features",
)
GEN = "risk.md:generated"
SECTIONS = (
    ("summary", "Summary"),
    ("abuse", "Who could be harmed and how"),
    ("guardrails", "Guardrails built in"),
    ("open", "Open questions"),
    ("accepted", "Accepted risks"),
    ("regimes", "Regimes that may apply"),
    ("legal", "Not legal advice"),
)


def load(path: Path = DATA) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the backstop


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text)


def _pattern(trigger: str, vocab: dict) -> re.Pattern[str]:
    """A trigger phrase as a regex: word boundaries, {name} -> vocab alternation, an
    optional plural or possessive ending, "'s" also matching a plural possessive."""
    body = ""
    for part in re.split(r"(\{\w+\})", trigger.lower()):
        if not part:
            continue
        m = re.fullmatch(r"\{(\w+)\}", part)
        if m:
            words = sorted(vocab[m.group(1)], key=len, reverse=True)
            body += (
                "(?:"
                + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in words)
                + ")"
            )
        else:
            lit = re.escape(part).replace(r"\ ", r"\s+").replace(" ", r"\s+")
            body += lit.replace("'s", "(?:'s|')")
    return re.compile(r"(?<![\w])" + body + r"(?:'s|s'|s|es)?(?![\w])")


def _first(text: str, triggers: list[str], vocab: dict) -> str | None:
    for t in triggers:
        m = _pattern(t, vocab).search(text)
        if m:
            return m.group(0)
    return None


def _all(text: str, triggers: list[str], vocab: dict) -> list[str]:
    out: list[str] = []
    for t in triggers:
        m = _pattern(t, vocab).search(text)
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


def backstop(
    text: str,
    sensitive: list | tuple = (),
    social: str | None = None,
    data: dict | None = None,
) -> dict:
    """{"categories": {id: [reasons]}, "stops": [{id, category, matched, ...}]}."""
    data = data or load()
    vocab, text = data["vocab"], _norm(text)
    found: dict[str, list[str]] = {}
    for cat in data["categories"]:
        hits = _all(text, cat["triggers"], vocab)
        if hits:
            found[cat["id"]] = [f"mentions '{h}'" for h in hits[:3]]
    for s in sensitive or ():
        cid = data["sensitive_map"].get(str(s).lower())
        if cid:
            found.setdefault(cid, []).append(f"constraints.sensitive lists {s}")
    cid = data["social_map"].get(str(social or ""))
    if cid:
        found.setdefault(cid, []).append(
            f"social.shape is {social} (people reach strangers)"
        )
    for rule in data.get("derive", []):
        if set(rule.get("categories_all", [])) <= set(found):
            hit = _first(text, rule["triggers"], vocab)
            if hit:
                found.setdefault(rule["category"], []).append(
                    f"{rule['why']} ('{hit}')"
                )
    stops = []
    for rule in data["stop_rules"]:
        hit = _first(text, rule["triggers"], vocab)
        when = rule.get("when") or {}
        if not hit and when:
            ok = True
            if "categories_any" in when:
                ok &= bool(set(when["categories_any"]) & set(found))
            if "categories_all" in when:
                ok &= set(when["categories_all"]) <= set(found)
            if "vocab_any" in when and ok:
                words = [w for name in when["vocab_any"] for w in vocab[name]]
                hit = _first(text, words, vocab)
                ok &= bool(hit)
            if not ok:
                hit = None
        if hit:
            stops.append(
                {
                    **{k: rule[k] for k in ("id", "category", "pattern", "reframe")},
                    "matched": hit,
                }
            )
    return {"categories": found, "stops": stops}


# ---------------------------------------------------------------- linting the data

CATEGORY_KEYS = (
    "id",
    "title",
    "tier_floor",
    "triggers",
    "questions",
    "guardrails",
    "regimes",
    "stop_patterns",
    "abuse_prompts",
)
CONTRACT_IDS = (
    "minors",
    "location",
    "health",
    "biometric",
    "financial",
    "ugc",
    "intimate",
    "surveillance",
    "ai_decisions",
    "regulated",
)
PACK_IDS = ("baseline", "location", "minors", "health", "ugc", "financial", "biometric")


def lint(data: dict) -> list[str]:
    """Problems with categories.json itself: the contract's ids and keys, 1-3 questions
    each with a phase and a why, known packs, and regimes linked to official sources."""
    out: list[str] = []
    ids = [c.get("id") for c in data.get("categories", [])]
    if tuple(ids) != CONTRACT_IDS:
        out.append(f"categories: ids {ids} are not the contract's {list(CONTRACT_IDS)}")
    if tuple(data.get("packs", {})) != PACK_IDS:
        out.append(
            f"packs: {list(data.get('packs', {}))} are not the contract's {list(PACK_IDS)}"
        )
    domains = data.get("official_domains", [])
    for c in data.get("categories", []):
        cid = c.get("id")
        missing = [k for k in CATEGORY_KEYS if k not in c]
        if missing:
            out.append(f"{cid}: missing {', '.join(missing)}")
            continue
        if c["tier_floor"] not in TIERS[:3]:
            out.append(
                f"{cid}: tier_floor {c['tier_floor']!r} is not one of standard, elevated, high"
            )
        if not 1 <= len(c["questions"]) <= 3:
            out.append(
                f"{cid}: {len(c['questions'])} questions (each category has 1-3 must-answer questions)"
            )
        if not any(q.get("ask_at") == "shape" for q in c["questions"]):
            out.append(
                f"{cid}: no question asked at shape (what changes the architecture?)"
            )
        for q in c["questions"]:
            if not str(q.get("id", "")).startswith(cid + "."):
                out.append(
                    f"{cid}: question id {q.get('id')!r} doesn't start with '{cid}.'"
                )
            if (
                q.get("ask_at") not in PHASES
                or not q.get("text")
                or not q.get("why")
                or not q.get("theme")
            ):
                out.append(
                    f"{q.get('id')}: needs text, why, theme and an ask_at in {', '.join(PHASES)}"
                )
        for p in c["guardrails"]:
            if p not in PACK_IDS:
                out.append(
                    f"{cid}: guardrail pack {p!r} is not one of {', '.join(PACK_IDS)}"
                )
        if not c["regimes"]:
            out.append(f"{cid}: no regimes (say which may apply, with official links)")
        for r in c["regimes"]:
            link = str(r.get("link", ""))
            host = re.sub(r"^https://([^/]+).*$", r"\1", link)
            if not (r.get("name") and r.get("applies_when")):
                out.append(f"{cid}: a regime needs name and applies_when")
            if not link.startswith("https://") or not any(
                host == d or host.endswith("." + d) for d in domains
            ):
                out.append(
                    f"{cid}: regime {r.get('name')!r} links {link!r}, not an official source in official_domains"
                )
        if not c["abuse_prompts"]:
            out.append(f"{cid}: no abuse prompts (who could use this to harm whom)")
        for t in c["triggers"]:
            try:
                _pattern(t, data["vocab"])
            except (KeyError, re.error) as e:
                out.append(f"{cid}: trigger {t!r} doesn't compile ({e})")
    for rule in data.get("stop_rules", []):
        if (
            rule.get("category") not in ids
            or not rule.get("pattern")
            or "reframe" not in rule
        ):
            out.append(
                f"stop rule {rule.get('id')!r}: needs a known category, a pattern and a reframe (or null)"
            )
    for combo in data.get("combinations", []):
        if not set(combo.get("all", [combo.get("any_with")])) <= set(
            ids
        ) or not combo.get("why"):
            out.append(f"combination {combo}: unknown category or no why")
    return out


# ---------------------------------------------------------------- tiers and plans


def _cats(data: dict) -> dict:
    return {c["id"]: c for c in data["categories"]}


def tier_of(ids, data: dict | None = None) -> tuple[str, list[str], list[str]]:
    """(tier, why it was raised, categories that need the owner's acknowledgment).
    The tier is the highest floor, raised one step (never into stop: only a stop rule
    reaches that) when a risky combination is present."""
    data = data or load()
    cats, ids = _cats(data), [i for i in ids if i in _cats(data)]
    if not ids:
        return "standard", [], []
    level = max(TIERS.index(cats[i]["tier_floor"]) for i in ids)
    raised, members = [], set()
    for combo in data["combinations"]:
        if "all" in combo and set(combo["all"]) <= set(ids):
            raised.append(combo["why"])
            members |= set(combo["all"])
        elif "any_with" in combo and combo["any_with"] in ids and len(ids) > 1:
            raised.append(combo["why"])
            members |= set(ids)
    if raised:
        level = min(level + 1, TIERS.index("high"))
    tier = TIERS[level]
    ack = []
    if tier == "high":
        ack = [i for i in ids if cats[i]["tier_floor"] == "high" or i in members]
    return tier, raised, ack


def packs_for(ids, data: dict | None = None) -> list[str]:
    data = data or load()
    cats, out = _cats(data), ["baseline"]
    for i in ids:
        for p in cats.get(i, {}).get("guardrails", []):
            if p not in out:
                out.append(p)
    return out


def plan(ids, data: dict | None = None) -> dict:
    """The questions to ask now (grouped by theme) and the ones to defer."""
    data = data or load()
    cats = _cats(data)
    now: dict[str, dict] = {}
    later = []
    for i in ids:
        for q in cats[i]["questions"]:
            if q["ask_at"] == "shape":
                g = now.setdefault(
                    q["theme"],
                    {"theme": q["theme"], "covers": [], "questions": [], "why": []},
                )
                g["covers"].append(q["id"])
                g["questions"].append(q["text"])
                g["why"].append(q["why"])
            else:
                later.append(
                    {
                        "id": q["id"],
                        "category": i,
                        "ask_at": q["ask_at"],
                        "text": q["text"],
                        "why": q["why"],
                    }
                )
    return {"ask_now": list(now.values()), "later": later}


def screen(text: str, sensitive=(), social=None, data: dict | None = None) -> dict:
    data = data or load()
    cats = _cats(data)
    bs = backstop(text, sensitive, social, data)
    ids = [c["id"] for c in data["categories"] if c["id"] in bs["categories"]]
    tier, raised, ack = tier_of(ids, data)
    if bs["stops"]:
        tier = "stop"
    return {
        "tier": tier,
        "categories": [
            {
                "id": i,
                "title": cats[i]["title"],
                "tier_floor": cats[i]["tier_floor"],
                "why": "; ".join(bs["categories"][i]),
                "source": "backstop",
            }
            for i in ids
        ],
        "raised_by": raised,
        "needs_ack": ack,
        "stop": bs["stops"],
        "packs": packs_for(ids, data),
        **plan(ids, data),
        "abuse_prompts": [
            {"category": i, "text": t} for i in ids for t in cats[i]["abuse_prompts"]
        ],
        "regimes": [{"category": i, **r} for i in ids for r in cats[i]["regimes"]],
        "not_legal_advice": data["not_legal_advice"],
    }


def idea_text(brief: dict) -> str:
    parts: list[str] = []

    def walk(v):
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    for k in IDEA_KEYS:
        walk(brief.get(k))
    return "\n".join(parts)


def screen_brief(brief: dict, data: dict | None = None) -> dict:
    constraints = (
        brief.get("constraints") if isinstance(brief.get("constraints"), dict) else {}
    )
    social = brief.get("social") if isinstance(brief.get("social"), dict) else {}
    return screen(
        idea_text(brief), constraints.get("sensitive") or (), social.get("shape"), data
    )


# ---------------------------------------------------------------- validating the brief


def _iso(s: object) -> bool:
    try:
        date.fromisoformat(str(s))
        return True
    except ValueError:
        return False


def validate(brief: object, data: dict | None = None) -> list[str]:
    """Problems with design/brief.json -> risk, one line each (empty when it's good)."""
    data = data or load()
    if not isinstance(brief, dict):
        return ["brief: not a JSON object"]
    risk = brief.get("risk")
    if not isinstance(risk, dict):
        return [
            "brief: no `risk` block (run the risk screen: "
            'python3 "$KIT/scripts/risk_screen.py" screen --brief design/brief.json; '
            "a standard idea records tier standard with empty lists)"
        ]
    cats = _cats(data)
    qcat = {q["id"]: (c["id"], q) for c in data["categories"] for q in c["questions"]}
    out: list[str] = []
    tier = risk.get("tier")
    if tier not in TIERS:
        return [f"risk: tier {tier!r} is not one of {', '.join(TIERS)}"]
    if tier == "stop":
        out.append(
            "risk: tier stop: the kit doesn't build a covert or non-consensual core. Offer the "
            "consented version (risk_screen.py screen prints it), record the declined part in "
            "risk.declined, and re-screen the idea you are building"
        )
    if risk.get("screened_at") not in PHASES:
        out.append(
            f"risk: screened_at {risk.get('screened_at')!r} is not one of {', '.join(PHASES)}"
        )
    for key in ("categories", "questions", "abuse_cases", "accepted", "declined"):
        if not isinstance(risk.get(key), list):
            out.append(f"risk: `{key}` must be a list (empty is fine)")
    if out and any("must be a list" in p for p in out):
        return out

    ids: list[str] = []
    for i, c in enumerate(risk["categories"]):
        cid = c.get("id") if isinstance(c, dict) else None
        if cid not in cats:
            out.append(
                f"risk.categories[{i}]: id {cid!r} is not one of {', '.join(cats)}"
            )
            continue
        if cid in ids:
            out.append(f"risk.categories: `{cid}` listed twice")
        ids.append(cid)
        if not c.get("why"):
            out.append(
                f"risk.categories `{cid}`: no `why` (what in the idea puts it here)"
            )
        if c.get("source") not in SOURCES:
            out.append(
                f"risk.categories `{cid}`: source {c.get('source')!r} is not one of {', '.join(SOURCES)}"
            )

    decisions = {
        d.get("id"): d for d in (brief.get("decisions") or []) if isinstance(d, dict)
    }
    seen_q: set[str] = set()
    for i, q in enumerate(risk["questions"]):
        if not isinstance(q, dict) or not q.get("id"):
            out.append(f"risk.questions[{i}]: needs an `id`")
            continue
        qid = q["id"]
        seen_q.add(qid)
        if q.get("category") not in cats:
            out.append(
                f"risk.questions `{qid}`: category {q.get('category')!r} is not a known category"
            )
        status = q.get("status")
        if status not in STATUSES:
            out.append(
                f"risk.questions `{qid}`: status {status!r} is not one of {', '.join(STATUSES)}"
            )
        if status in ("asked", "default") and not q.get("answer"):
            out.append(f"risk.questions `{qid}`: status {status} needs an answer")
        if status == "deferred" and qid in qcat and qcat[qid][1]["ask_at"] == "shape":
            out.append(
                f"risk.questions `{qid}`: it changes the architecture, so it's settled at shape: "
                "ask it or state a default"
            )
        dec = q.get("decision", qid)
        if dec not in decisions:
            out.append(
                f"risk.questions `{qid}`: no `decisions` entry `{dec}` (every risk question goes in "
                "the ledger too; one decision may cover several, via `decision`)"
            )
    for cid in ids:
        for q in cats[cid]["questions"]:
            if q["id"] not in seen_q:
                out.append(
                    f"risk: `{q['id']}` ({cid}) is not in risk.questions: ask it, state a default, "
                    f"or defer it (ask_at {q['ask_at']})"
                )

    if tier in ("elevated", "high"):
        if not risk["abuse_cases"]:
            out.append(
                f"risk: tier {tier} needs at least one abuse case (who could use this to harm whom, "
                "and what in the design stops it)"
            )
    for i, a in enumerate(risk["abuse_cases"]):
        missing = [k for k in ABUSE_KEYS if not (isinstance(a, dict) and a.get(k))]
        if missing:
            out.append(f"risk.abuse_cases[{i}]: missing {', '.join(missing)}")
    for i, a in enumerate(risk["accepted"]):
        missing = [k for k in ACCEPT_KEYS if not (isinstance(a, dict) and a.get(k))]
        if missing:
            out.append(f"risk.accepted[{i}]: missing {', '.join(missing)}")
        elif not _iso(a["on"]):
            out.append(f"risk.accepted[{i}]: on {a['on']!r} is not a date (YYYY-MM-DD)")
    for i, d in enumerate(risk["declined"]):
        if not (isinstance(d, dict) and d.get("item") and d.get("why")):
            out.append(
                f"risk.declined[{i}]: needs `item` and `why` (and the `reframe` offered)"
            )

    # The floor: the categories' own tier, then the keyword backstop.
    bs = screen_brief(brief, data)
    for c in bs["categories"]:
        if c["id"] not in ids:
            out.append(
                f"risk: the backstop finds `{c['id']}` ({c['why']}) but risk.categories doesn't list "
                "it: add categories freely, never drop one the backstop found"
            )
    floor_ids = list(dict.fromkeys(ids + [c["id"] for c in bs["categories"]]))
    floor, _, ack = tier_of(floor_ids, data)
    if tier != "stop" and TIERS.index(tier) < TIERS.index(floor):
        out.append(
            f"risk: tier {tier} is lower than the backstop's {floor} "
            f"({', '.join(floor_ids)}): the agent may raise a tier, never lower it"
        )
    if bs["stop"] and tier != "stop" and not risk["declined"]:
        s = bs["stop"][0]
        out.append(
            f"risk: the backstop finds a stop pattern ({s['pattern']} Matched '{s['matched']}'): "
            "decline that core, offer the consented version, and record it in risk.declined"
        )
    if tier == "high" or floor == "high":
        # Raised to high by judgment rather than by the rules: every listed category
        # needs the owner's acknowledgment.
        for cid in ack or ids:
            if not any(
                isinstance(a, dict)
                and a.get("by") == "owner"
                and (
                    a.get("item") == cid or str(a.get("item", "")).startswith(cid + ".")
                )
                for a in risk["accepted"]
            ):
                out.append(
                    f"risk: tier high and no owner acknowledgment for `{cid}` (risk.accepted: item "
                    f"`{cid}` or `{cid}.<question>`, by owner, on, note)"
                )
    return out


# ---------------------------------------------------------------- RISK.md


def _q_text(qid: str, data: dict, decisions: dict) -> str:
    for c in data["categories"]:
        for q in c["questions"]:
            if q["id"] == qid:
                return q["text"]
    return str((decisions.get(qid) or {}).get("question") or qid)


def _cell(v: object) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def _block_body(key: str, brief: dict, data: dict) -> list[str]:
    risk = brief.get("risk") or {}
    cats = _cats(data)
    ids = [
        c["id"]
        for c in risk.get("categories") or []
        if isinstance(c, dict) and c.get("id") in cats
    ]
    decisions = {
        d.get("id"): d for d in brief.get("decisions") or [] if isinstance(d, dict)
    }
    tier = risk.get("tier", "standard")
    if key == "summary":
        _, raised, _ = tier_of(ids, data)
        head = f"**Tier: {tier}.**"
        if raised:
            head += " Raised one step: " + "; ".join(raised) + "."
        if not ids:
            head += " Nothing in the idea touches a sensitive category, so the baseline guardrails are all it needs."
        lines = [head, ""]
        for c in risk.get("categories") or []:
            if isinstance(c, dict) and c.get("id") in cats:
                lines.append(
                    f"- **{cats[c['id']]['title']}** (`{c['id']}`, {c.get('source', 'inferred')}): {c.get('why', '')}"
                )
        for d in risk.get("declined") or []:
            if isinstance(d, dict):
                offer = f" Offered instead: {d['reframe']}" if d.get("reframe") else ""
                lines.append(
                    f"- **Declined:** {d.get('item', '')}. {d.get('why', '')}{offer}"
                )
        return lines
    if key == "abuse":
        rows = [a for a in risk.get("abuse_cases") or [] if isinstance(a, dict)]
        if not rows:
            return ["None recorded: a standard idea needs none."]
        return [
            "| Who | Could do this | What in the design stops it |",
            "|---|---|---|",
            *(
                "| " + " | ".join(_cell(a.get(k, "")) for k in ABUSE_KEYS) + " |"
                for a in rows
            ),
        ]
    if key == "guardrails":
        lines = []
        for p in packs_for(ids, data):
            pk = data["packs"].get(p, {})
            lines.append(f"- **{pk.get('title', p)}** (`{p}`): {pk.get('guards', '')}")
        lines += [
            "",
            "Turned on in the app's `privacy/data-map.yaml` -> `packs`; each pack's checks run in the app's gates.",
        ]
        return lines
    if key == "open":
        lines = []
        for q in risk.get("questions") or []:
            if isinstance(q, dict) and q.get("status") == "deferred":
                d = decisions.get(q.get("decision", q.get("id"))) or {}
                lines.append(
                    f"- `{q.get('id')}` ({q.get('category')}, ask at {d.get('ask_at', '?')}): "
                    f"{_q_text(str(q.get('id')), data, decisions)}"
                )
        return lines or ["None open."]
    if key == "accepted":
        lines = [
            f"- `{a.get('item')}`: {a.get('note', '')} ({a.get('by')}, {a.get('on')})"
            for a in risk.get("accepted") or []
            if isinstance(a, dict)
        ]
        return lines or ["None recorded."]
    if key == "regimes":
        lines = []
        for cid in ids:
            lines.append(f"**{cats[cid]['title']}**")
            lines.append("")
            lines += [
                f"- [{r['name']}]({r['link']}): may apply when {r['applies_when']}"
                for r in cats[cid]["regimes"]
            ]
            lines.append("")
        return (
            lines[:-1]
            if lines
            else ["None beyond the general privacy law where your users live."]
        )
    if key == "legal":
        return [data["not_legal_advice"]]
    raise KeyError(key)


def block(key: str, brief: dict, data: dict) -> str:
    return "\n".join(
        [
            f"<!-- {GEN}:{key} -->",
            *_block_body(key, brief, data),
            f"<!-- /{GEN}:{key} -->",
        ]
    )


def _block_re(key: str) -> re.Pattern[str]:
    return re.compile(
        rf"<!-- {re.escape(GEN)}:{key} -->.*?<!-- /{re.escape(GEN)}:{key} -->", re.S
    )


def fresh(brief: dict, data: dict) -> str:
    name = ((brief.get("app") or {}).get("name")) or "the app"
    parts = [
        f"# Risk and trust: {name}",
        "",
        "<!-- Generated from design/brief.json -> risk by the App in a Box risk screen",
        "     (risk_screen.py render). The text between risk.md:generated markers is",
        "     rewritten on every run; anything you write outside them is kept. Change the",
        "     risk block in the brief, then regenerate. -->",
        "",
    ]
    for key, heading in SECTIONS:
        parts += [f"## {heading}", "", block(key, brief, data), ""]
    return "\n".join(parts)


def update(text: str | None, brief: dict, data: dict) -> str:
    if not text:
        return fresh(brief, data)
    for key, heading in SECTIONS:
        new = block(key, brief, data)
        pat = _block_re(key)
        if pat.search(text):
            text = pat.sub(lambda _m, new=new: new, text, count=1)
            continue
        head = re.search(rf"^## {re.escape(heading)}[ \t]*\n", text, re.M)
        if head:
            text = text[: head.end()] + "\n" + new + "\n" + text[head.end() :]
        else:
            text = text.rstrip("\n") + f"\n\n## {heading}\n\n{new}\n"
    return text


def drift(text: str, brief: dict, data: dict, name: str = "RISK.md") -> list[str]:
    errs = []
    for key, _ in SECTIONS:
        found = _block_re(key).findall(text)
        if not found:
            errs.append(f"{name}: generated block '{key}' is missing")
        elif len(found) > 1:
            errs.append(f"{name}: generated block '{key}' appears {len(found)} times")
        elif found[0] != block(key, brief, data):
            errs.append(
                f"{name}: generated block '{key}' differs from design/brief.json -> risk"
            )
    return errs


# ---------------------------------------------------------------- CLI


def _read_brief(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("screen", help="classify an idea or a brief; prints JSON")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--idea")
    g.add_argument("--brief")
    sub.add_parser("check", help="validate design/brief.json -> risk").add_argument(
        "brief"
    )
    r = sub.add_parser("render", help="write or check docs/product/RISK.md")
    r.add_argument("brief")
    r.add_argument("--out", default="docs/product/RISK.md")
    r.add_argument("--check", action="store_true")
    sub.add_parser("packs", help="the guardrail packs the brief turns on").add_argument(
        "brief"
    )
    sub.add_parser("lint", help="check categories.json itself").add_argument(
        "data", nargs="?", default=str(DATA)
    )
    a = ap.parse_args(argv)
    if a.cmd == "lint":
        try:
            problems = lint(load(Path(a.data)))
        except (OSError, ValueError) as e:
            problems = [f"{a.data}: can't read: {e}"]
        for p in problems:
            print(p)
        return 1 if problems else 0
    data = load()
    try:
        brief = _read_brief(a.brief) if getattr(a, "brief", None) else None
    except (OSError, ValueError) as e:
        print(f"brief: can't read {a.brief}: {e}")
        return 2
    if a.cmd == "screen":
        res = (
            screen(a.idea, data=data)
            if a.idea is not None
            else screen_brief(brief or {}, data)
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "check":
        problems = validate(brief, data)
        for p in problems:
            print(p)
        return 1 if problems else 0
    if a.cmd == "packs":
        risk = (brief or {}).get("risk") or {}
        ids = [c.get("id") for c in risk.get("categories") or [] if isinstance(c, dict)]
        print("\n".join(packs_for(ids, data)))
        return 0
    out = Path(a.out)
    if a.check:
        if not out.is_file():
            print(
                f"{a.out}: missing. Generate it: python3 risk_screen.py render {a.brief} --out {a.out}"
            )
            return 1
        errs = drift(out.read_text(encoding="utf-8"), brief or {}, data, a.out)
        for e in errs:
            print(e)
        return 1 if errs else 0
    old = out.read_text(encoding="utf-8") if out.is_file() else None
    new = update(old, brief or {}, data)
    if new != old:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(new, encoding="utf-8")
    print(f"{'wrote' if new != old else 'unchanged:'} {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
