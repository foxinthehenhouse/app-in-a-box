#!/usr/bin/env python3
"""The launch gate for the idea's risk screen, and the owner's compliance checklist.

    python3 scripts/risk_gate.py check                 # ship runs this first; exit 1 = blocked
    python3 scripts/risk_gate.py open --json           # what `next` surfaces
    python3 scripts/risk_gate.py checklist [--check]   # docs/product/COMPLIANCE.md
    python3 scripts/risk_gate.py rescreen --text "..." # a feature touched a new category?
    python3 scripts/risk_gate.py rescreen --file docs/product/SCREENS.md

Shape screens the idea and records it in design/brief.json -> `risk` (tier, categories,
questions, abuse cases, accepted risks); docs/product/RISK.md is the readable copy. This
script reads that block and nothing else decides for it:

- `check` refuses while a risk question is open, while an accepted risk has no owner
  (`by`) or no date (`on`), while a high-tier category has no answered question and no
  accepted item, or while SCREENS.md or a spec mentions a category the screen never
  covered. It names each item. Passing is not a compliance sign-off and never says so.
- `rescreen` matches a feature's text against the categories' trigger words. A new
  category is added to the brief with its must-answer questions opened and the tier
  raised, so the gate holds until the owner answers them. If the kit's `risk_screen.py`
  is reachable it is asked to do the full screen first; this is the backstop.
- `checklist` writes a per-category list for the owner: store guidelines, age-rating
  answers, a pointer to the privacy labels, the regimes that may apply (with links) and,
  at tier high, "talk to counsel". Ticks you make inside it survive a regeneration.

Category data (trigger words, questions, tier floors, regimes) lives in the App in a
Box kit at scripts/risk/categories.json. It is looked up at --categories, then
$APPBOX_RISK_CATEGORIES, then the kit this file sits in (when run from the kit), then
$CLAUDE_PLUGIN_ROOT. Without it the gate still checks questions and accepted risks, and
treats every category as high-tier at tier high (the stricter reading); the doc scan
and re-screen say they couldn't run instead of passing quietly.

Not legal advice. Standard library only. Exit 0 = clear, 1 = blocked / drift / new
category (rescreen --check), 2 = usage, 3 = rescreen couldn't run (no category data or
no screen yet; it says what to do instead).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TIERS = ("standard", "elevated", "high", "stop")
# Risky combinations raise the idea one tier (docs/specs/trust-by-default in the kit).
COMBOS = (("minors", "location"), ("minors", "ugc"), ("health", "ai_decisions"))
RESOLVED = {"asked", "answered", "resolved", "default"}
BRIEF = Path("design") / "brief.json"
OUT = Path("docs") / "product" / "COMPLIANCE.md"
SCANNED = ("docs/product/SCREENS.md", "docs/product/specs")
START, END = "<!-- risk:generated:checklist -->", "<!-- /risk:generated:checklist -->"

APPLE = "https://developer.apple.com/app-store/review/guidelines/"
PLAY = "https://play.google/developer-content-policy/"
APPLE_PRIVACY = "https://developer.apple.com/app-store/app-privacy-details/"
PLAY_SAFETY = "https://support.google.com/googleplay/android-developer/answer/10787469"

# What each category asks of the stores. Section numbers are the App Store Review
# Guidelines'; Play names are its Policy Center's. Both change: the owner checks the
# live text, this only says where to look.
STORE: dict[str, dict[str, list[str]]] = {
    "minors": {
        "store": [
            "Apple 1.3 (Kids Category) and 5.1.4 (Kids): no third-party analytics or ads "
            "in a kids app, parental gate before links out or purchases",
            "Google Play Families policy: set the target audience honestly; under-13s "
            "bring the Families requirements (ads, SDKs, data)",
        ],
        "age": [
            "The age rating reflects content, not audience: a kids app is still rated on "
            "what it shows. If under-13s are the audience, pick Apple's Kids age band and "
            "Play's target-audience ages to match",
        ],
    },
    "location": {
        "store": [
            "Apple 5.1.1 and 5.1.5 (Location Services): ask only when the feature needs "
            "it, and say why in the permission string",
            "Google Play location permissions: background location needs a declaration "
            "in Play Console and a prominent in-app disclosure",
        ],
        "age": [
            "Both questionnaires ask whether the app shares a user's location with other "
            "users: answer for what the app actually does",
        ],
    },
    "health": {
        "store": [
            "Apple 5.1.3 (Health and Health Research): health data never goes to "
            "advertising or data brokers; 1.4.1 if the app could cause physical harm",
            "Google Play Health Content and Services policy, and the health apps "
            "declaration in Play Console (plus Health Connect permissions if you use it)",
        ],
        "age": [
            "Apple's questionnaire asks about medical or treatment information: answer "
            "yes if the app gives it",
        ],
    },
    "biometric": {
        "store": [
            "Apple 5.1.1 and 5.1.2: say why in NSFaceIDUsageDescription; face or body "
            "data is used only for the stated purpose",
            "Google Play User Data policy: prominent disclosure and consent before "
            "collecting biometric data",
        ],
        "age": ["No age-rating question of its own: answer the content questions honestly"],
    },
    "financial": {
        "store": [
            "Apple 3.1 (payments): digital goods go through in-app purchase; 5.1.1 for "
            "the financial data you collect",
            "Google Play Financial Services and Payments policies (and the financial "
            "features declaration in Play Console)",
        ],
        "age": ["No age-rating question of its own: answer the content questions honestly"],
    },
    "ugc": {
        "store": [
            "Apple 1.2 (User-Generated Content): a way to filter objectionable content, "
            "report it, block abusive users, and published contact details",
            "Google Play User Generated Content policy: in-app reporting and moderation "
            "that acts on reports",
        ],
        "age": [
            "Both questionnaires ask whether users can talk to each other or share "
            "content: answer yes",
        ],
    },
    "intimate": {
        "store": [
            "Apple 1.1.4 (overtly sexual content) and 1.2 (user-generated content)",
            "Google Play Sexual Content and Profanity policy (dating apps have extra "
            "rules there)",
        ],
        "age": [
            "Expect the top age band: answer the sexual-content and mature-themes "
            "questions for what users can see, including other users' content",
        ],
    },
    "surveillance": {
        "store": [
            "Apple 5.1.1 and 5.1.2: the monitored person knows and agrees; data is used "
            "only for what they agreed to",
            "Google Play stalkerware rules: a monitoring app must disclose itself, show "
            "a persistent notice, and never hide its icon",
        ],
        "age": ["No age-rating question of its own: answer the content questions honestly"],
    },
    "ai_decisions": {
        "store": [
            "Apple 5.1.2: say clearly when personal data goes to a third-party AI, and "
            "get permission first",
            "Google Play AI-Generated Content policy: users can report offensive output",
        ],
        "age": ["No age-rating question of its own: answer the content questions honestly"],
    },
    "regulated": {
        "store": [
            "Apple 5.3 (gaming, gambling, lotteries), 3.1.5 (cryptocurrencies) or 1.4.1 "
            "(medical): most need a licence and an organisation account",
            "Google Play Real-Money Gambling and Financial Services policies: country "
            "lists, licences and an application before launch",
        ],
        "age": [
            "Simulated and real-money gambling are separate questions; real money means "
            "the top age band",
        ],
    },
}


# ---- inputs (all defensive: a malformed file is a reason, never a crash) -----------


def load_brief(root: Path) -> tuple[dict | None, str | None]:
    try:
        brief = json.loads((root / BRIEF).read_text(encoding="utf-8"))
    except OSError:
        return None, f"{BRIEF} not found: run the App in a Box shape skill first"
    except ValueError as e:
        return None, f"{BRIEF} is not valid JSON ({e})"
    if not isinstance(brief, dict):
        return None, f"{BRIEF} is not a JSON object"
    return brief, None


def category_paths(given: str | None) -> list[Path]:
    here = Path(__file__).resolve()
    paths = [Path(p) for p in (given, os.environ.get("APPBOX_RISK_CATEGORIES")) if p]
    if here.parent.parent.name == "template":  # running from inside the kit
        paths.append(here.parents[2] / "scripts" / "risk" / "categories.json")
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        paths.append(
            Path(os.environ["CLAUDE_PLUGIN_ROOT"]) / "scripts" / "risk" / "categories.json"
        )
    return paths


def load_categories(given: str | None) -> dict[str, dict] | None:
    """Category id -> entry, or None when no categories file can be found or read."""
    for path in category_paths(given):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = raw.get("categories", raw) if isinstance(raw, dict) else raw
        if isinstance(entries, dict):  # also accept {id: entry}
            entries = [dict(v, id=k) for k, v in entries.items() if isinstance(v, dict)]
        if isinstance(entries, list):
            out = {
                e["id"]: e for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)
            }
            if out:
                return out
    return None


def as_list(value: object) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def tier_of(value: object) -> str:
    return value if isinstance(value, str) and value in TIERS else "standard"


# ---- the gate ------------------------------------------------------------------------


def bad_accepted(risk: dict) -> tuple[list[str], list[dict]]:
    """Problems with accepted risks, and the entries that are valid."""
    problems, valid = [], []
    for i, a in enumerate(risk.get("accepted") or []):
        if not isinstance(a, dict):
            problems.append(f"accepted[{i}] is not an object")
            continue
        name = a.get("item") if isinstance(a.get("item"), str) and a.get("item") else None
        label = f"accepted risk `{name}`" if name else f"accepted[{i}]"
        missing = []
        if not name:
            missing.append("no `item` (which question or category it accepts)")
        if not (isinstance(a.get("by"), str) and a["by"].strip()):
            missing.append("no owner (`by`)")
        try:
            datetime.date.fromisoformat(str(a.get("on")))
        except ValueError:
            missing.append("no date (`on`, YYYY-MM-DD)")
        if missing:
            problems.append(f"{label} is rejected: {', '.join(missing)}. An accepted risk "
                            "is a recorded owner decision, so it needs who and when")  # fmt: skip
        else:
            valid.append(a)
    return problems, valid


def question_text(qid: str, categories: dict[str, dict] | None) -> str:
    for cat in (categories or {}).values():
        for q in as_list(cat.get("questions")):
            if q.get("id") == qid and isinstance(q.get("text"), str):
                return q["text"]
    return ""


def matches(text: str, categories: dict[str, dict]) -> dict[str, str]:
    """Category id -> the first trigger word found in text (word-bounded, plurals ok)."""
    low, found = text.lower(), {}
    for cid, cat in categories.items():
        for trig in cat.get("triggers") or []:
            if not isinstance(trig, str) or not trig.strip():
                continue
            pat = r"(?<![a-z0-9])" + re.escape(trig.lower().strip()) + r"(?:s|es)?(?![a-z0-9])"
            if re.search(pat, low):
                found[cid] = trig
                break
    return found


def covered(risk: dict, valid_accepted: list[dict]) -> set[str]:
    """Categories the screen already covers: screened in, or accepted out by the owner
    (an accepted item naming the category itself, e.g. a map that only shows shops)."""
    ids = {c.get("id") for c in as_list(risk.get("categories"))}
    return {i for i in ids if isinstance(i, str)} | {a["item"] for a in valid_accepted}


def scanned_docs(root: Path) -> list[Path]:
    out = []
    for rel in SCANNED:
        p = root / rel
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(p.rglob("*.md")))
    return out


def uncovered_in_docs(root: Path, risk: dict, valid: list[dict], categories: dict[str, dict]):
    have, out = covered(risk, valid), []
    for doc in scanned_docs(root):
        try:
            text = doc.read_text(encoding="utf-8")
        except OSError:
            continue
        for cid, word in matches(text, categories).items():
            if cid not in have and cid not in {c for _, c, _ in out}:
                out.append((doc.relative_to(root).as_posix(), cid, word))
    return out


def blockers(root: Path, categories: dict[str, dict] | None, scan_docs: bool = True) -> list[str]:
    brief, err = load_brief(root)
    if brief is None:
        return [err or f"{BRIEF} unreadable"]
    risk = brief.get("risk")
    if not isinstance(risk, dict):
        return [
            "the idea was never risk-screened (design/brief.json has no `risk` block): run "
            "the risk step of the App in a Box shape skill before launch"
        ]
    tier = tier_of(risk.get("tier"))
    out: list[str] = []
    if tier == "stop":
        out.append("tier is `stop`: the screen declined this design's core. Build the "
                   "consented version the screen offered, then re-screen")  # fmt: skip
    problems, valid = bad_accepted(risk)
    out += problems
    accepted_ids = {a["item"] for a in valid}

    answered: dict[str, int] = {}
    for q in as_list(risk.get("questions")):
        qid = str(q.get("id") or "?")
        cat = str(q.get("category") or qid.split(".")[0])
        done = q.get("status") in RESOLVED and bool(str(q.get("answer") or "").strip())
        if done or qid in accepted_ids:
            answered[cat] = answered.get(cat, 0) + 1
            continue
        text = question_text(qid, categories)
        ask_at = f", parked until {q['ask_at']}" if q.get("ask_at") else ""
        said = f": {text.rstrip()}" if text else ""
        stop = "" if said[-1:] in ("?", ".", "!") else "."
        out.append(f"open question `{qid}` ({cat}{ask_at}){said}{stop} Answer it, or record "
                   "it under risk.accepted with who and when")  # fmt: skip

    for c in as_list(risk.get("categories")):
        cid = str(c.get("id") or "?")
        floor = tier_of((categories or {}).get(cid, {}).get("tier_floor"))
        high = TIERS.index(floor) >= 2 if categories else TIERS.index(tier) >= 2
        has_accept = any(a == cid or a.startswith(cid + ".") for a in accepted_ids)
        if high and not answered.get(cid) and not has_accept:
            out.append(f"high-tier category `{cid}` has no resolved or accepted item: answer "
                       "one of its questions or record an accepted risk for it")  # fmt: skip

    if scan_docs and categories:
        for doc, cid, word in uncovered_in_docs(root, risk, valid, categories):
            out.append(f"{doc} mentions `{cid}` ('{word}') but the risk screen never covered "
                       "it: run `python3 scripts/risk_gate.py rescreen --file " + doc + "`")  # fmt: skip
    return out


def cmd_check(a: argparse.Namespace) -> int:
    root = Path(a.app)
    categories = load_categories(a.categories)
    found = blockers(root, categories)
    if found:
        print(f"risk gate: BLOCKED, {len(found)} open risk item(s). Ship waits for each:")
        for item in found:
            print(f"  - {item}")
        return 1
    brief, _ = load_brief(root)
    tier = tier_of(((brief or {}).get("risk") or {}).get("tier"))
    print(f"risk gate: no open risk items (tier {tier}).")
    if categories is None:
        print("  (category data not found, so SCREENS.md and specs were not scanned for new "
              "categories; pass --categories <kit>/scripts/risk/categories.json)")  # fmt: skip
    print("  Next: go through docs/product/COMPLIANCE.md with the owner "
          "(`python3 scripts/risk_gate.py checklist`).")  # fmt: skip
    print("  This is not a compliance sign-off and not legal advice.")
    return 0


def cmd_open(a: argparse.Namespace) -> int:
    root = Path(a.app)
    brief, _ = load_brief(root)
    risk = (brief or {}).get("risk")
    # An app that was never screened, or has no brief yet, is setup's business, not next's.
    items = blockers(root, load_categories(a.categories)) if isinstance(risk, dict) else []
    if a.json:
        print(json.dumps({"tier": tier_of((risk or {}).get("tier")) if isinstance(risk, dict)
                          else None, "open": items}, indent=2))  # fmt: skip
    else:
        print("\n".join(items) or "no open risk items")
    return 0


# ---- re-screen ----------------------------------------------------------------------


def screen_script(app: Path) -> Path | None:
    """The kit's full screen, if reachable. APPBOX_RISK_SCREEN=none turns delegation off."""
    env = os.environ.get("APPBOX_RISK_SCREEN")
    if env == "none":
        return None
    here = Path(__file__).resolve()
    cands = [Path(env)] if env else []
    kits = [here.parents[2]] if here.parent.parent.name == "template" else []
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        kits.append(Path(os.environ["CLAUDE_PLUGIN_ROOT"]))
    for kit in kits:
        cands += [kit / "scripts" / "risk_screen.py", kit / "scripts" / "risk" / "risk_screen.py"]
    cands.append(app / "scripts" / "risk_screen.py")
    return next((c for c in cands if c.is_file()), None)


def computed_tier(ids: list[str], categories: dict[str, dict]) -> str:
    level = max([TIERS.index(tier_of(categories.get(i, {}).get("tier_floor"))) for i in ids] or [0])
    s = set(ids)
    combo = any(x in s and y in s for x, y in COMBOS) or ("surveillance" in s and len(s) > 1)
    if combo and level < TIERS.index("high"):  # a combination never reaches stop alone
        level += 1
    return TIERS[level]


def apply_rescreen(brief: dict, new: dict[str, str], categories: dict[str, dict], src: str):
    risk = brief["risk"]
    cats = risk.setdefault("categories", [])
    qs = risk.setdefault("questions", [])
    have_q = {q.get("id") for q in as_list(qs)}
    opened = []
    for cid, word in new.items():
        cats.append({"id": cid, "why": f"re-screen: {src} mentions '{word}'", "source": "rescreen"})
        for q in as_list(categories[cid].get("questions")):
            if q.get("id") and q["id"] not in have_q:
                qs.append({"id": q["id"], "category": cid, "status": "open", "answer": None})
                opened.append(q["id"])
    ids = [str(c.get("id")) for c in as_list(cats)]
    before = tier_of(risk.get("tier"))
    after = TIERS[max(TIERS.index(before), TIERS.index(computed_tier(ids, categories)))]
    risk["tier"] = after
    return before, after, opened


def cmd_rescreen(a: argparse.Namespace) -> int:
    root = Path(a.app)
    categories = load_categories(a.categories)
    if categories is None:
        print("risk rescreen: category data not found, so this can't screen the feature. "
              "Run the risk step of the App in a Box shape skill on it, or pass "
              "--categories <kit>/scripts/risk/categories.json")  # fmt: skip
        return 3
    brief, err = load_brief(root)
    if brief is None or not isinstance(brief.get("risk"), dict):
        print(f"risk rescreen: {err or 'the idea was never screened (no risk block)'}: "
              "run the risk step of the App in a Box shape skill first")  # fmt: skip
        return 3
    if a.text:
        text, src = a.text, "the feature"
    else:
        files = [root / f for f in a.file] if a.file else scanned_docs(root)
        text = "\n".join(f.read_text(encoding="utf-8") for f in files if f.is_file())
        src = ", ".join(f.relative_to(root).as_posix() if f.is_relative_to(root) else str(f)
                        for f in files) or "nothing"  # fmt: skip
    _, valid = bad_accepted(brief["risk"])
    new = {c: w for c, w in matches(text, categories).items()
           if c not in covered(brief["risk"], valid)}  # fmt: skip
    if not new:
        print(f"risk rescreen: no new category in {src}. The screen still holds.")
        return 0
    names = ", ".join(f"`{c}` ('{w}')" for c, w in new.items())
    if a.check:
        print(f"risk rescreen: {src} touches a category the screen never covered: {names}. "
              "Run `python3 scripts/risk_gate.py rescreen` without --check")  # fmt: skip
        return 1
    script = screen_script(root)
    if script:  # the full screen first; whatever it leaves uncovered, the backstop adds
        try:
            r = subprocess.run([sys.executable, str(script), "rescreen", "--app", str(root),
                                "--text", text], capture_output=True, text=True, timeout=120)  # fmt: skip
            print(r.stdout.strip() or f"({script.name} exited {r.returncode})")
        except (OSError, subprocess.SubprocessError) as e:
            print(f"({script.name} didn't run: {e}; using the backstop)")
        brief, _ = load_brief(root)
        if brief is None or not isinstance(brief.get("risk"), dict):
            return 1
        _, valid = bad_accepted(brief["risk"])
        new = {c: w for c, w in new.items() if c not in covered(brief["risk"], valid)}
    if new:
        before, after, opened = apply_rescreen(brief, new, categories, src)
        (root / BRIEF).write_text(
            json.dumps(brief, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"risk rescreen: new category {names}; tier {before} -> {after}.")
        if opened:
            print(f"  Opened {len(opened)} must-answer question(s): {', '.join(opened)}.")
    print("  Next, before building it: ask the owner the opened questions (one structured "
          "round), write each answer back to design/brief.json -> risk.questions, add a "
          "misuse case for the new category (who could use it to harm whom, and what stops "
          "it), then regenerate docs/product/RISK.md with the shape risk step and "
          "`python3 scripts/risk_gate.py checklist`. Ship refuses until they're answered.")  # fmt: skip
    return 0


# ---- the owner's checklist ----------------------------------------------------------


def checklist_body(root: Path, risk: dict, categories: dict[str, dict] | None) -> str:
    tier = tier_of(risk.get("tier"))
    _, valid = bad_accepted(risk)
    has_map = (root / "privacy" / "data-map.yaml").is_file()
    labels = ("drafted from `privacy/data-map.yaml`" if has_map
              else "drafted from the migrations, `mobile/lib/analytics.ts` and the SDKs "
                   "(`ship` step 3)")  # fmt: skip
    lines = [
        f"_Generated from `design/brief.json` → `risk` by `scripts/risk_gate.py checklist`. "
        f"Tier: **{tier}**. Tick items as you check them; ticks survive a regeneration._",
        "",
        "> This is a list of things for you to check before launch. It is not a statement "
        "that the app complies with any law, regulation or store rule, and it isn't legal "
        "advice. Laws differ by country and change.",
    ]
    if TIERS.index(tier) >= 2:
        lines += [
            ">",
            "> **Talk to counsel before launch.** This idea screened as tier "
            f"**{tier}**: have a lawyer who knows these regimes look at the design, the "
            "privacy policy and the accepted risks below before the first public release.",
        ]
    lines += [
        "",
        "### Every app",
        "",
        f"- [ ] Privacy labels: the App Store privacy details ({APPLE_PRIVACY}) and the "
        f"Play data safety form ({PLAY_SAFETY}), {labels}. The owner submits them.",
        "- [ ] Account deletion inside the app, with the user's data (Apple 5.1.1(v)), and "
        "a web URL for it (Google Play).",
        "- [ ] A privacy policy URL and a support URL in both store listings.",
        "- [ ] Age rating: answer Apple's age-rating questionnaire and Play's content "
        "rating (IARC) questionnaire for what the app does today. Each category below "
        "says which answers it points to.",
    ]
    for c in as_list(risk.get("categories")):
        cid = str(c.get("id") or "?")
        entry = (categories or {}).get(cid, {})
        title = entry.get("title") if isinstance(entry.get("title"), str) else cid
        store = STORE.get(cid, {})
        lines += ["", f"### {title} (`{cid}`)", ""]
        if c.get("why"):
            lines += [f"Why it's here: {c['why']}", ""]
        lines.append(f"Store guidelines ([App Store]({APPLE}), [Google Play]({PLAY})):")
        lines += [f"- [ ] {s}" for s in store.get("store") or
                  ["Search both stores' guidelines for this category and note what applies"]]  # fmt: skip
        lines += ["", "Age rating:"]
        lines += [f"- [ ] {s}" for s in store.get("age") or
                  ["Answer the content questions honestly for this feature"]]  # fmt: skip
        lines += ["", "Regimes that may apply (whether they do depends on where your users "
                  "are and what you hold; a lawyer can say):"]  # fmt: skip
        regimes = as_list(entry.get("regimes"))
        if regimes:
            for r in regimes:
                link = f" ({r['link']})" if r.get("link") else ""
                when = f": {r['applies_when']}" if r.get("applies_when") else ""
                lines.append(f"- [ ] {r.get('name', '?')}{when}{link}")
        elif categories is None:
            lines.append("- Category data wasn't found, so none are listed. Re-run with "
                         "`--categories <kit>/scripts/risk/categories.json`.")  # fmt: skip
        else:
            lines.append("- None listed for this category.")
        mine = [a for a in valid if a["item"] == cid or a["item"].startswith(cid + ".")]
        if mine:
            lines += ["", "Accepted risks (the owner's recorded calls):"]
            lines += [f"- `{a['item']}`, by {a['by']} on {a['on']}"
                      + (f": {a['note']}" if a.get("note") else "") for a in mine]  # fmt: skip
    return "\n".join(lines)


def keep_ticks(body: str, old_block: str) -> str:
    ticked = {m.group(1) for m in re.finditer(r"^- \[[xX]\] (.+)$", old_block, re.M)}
    return "\n".join("- [x] " + ln[6:] if ln.startswith("- [ ] ") and ln[6:] in ticked else ln
                     for ln in body.splitlines())  # fmt: skip


def render_checklist(root: Path, risk: dict, categories: dict[str, dict] | None, old: str) -> str:
    body = checklist_body(root, risk, categories)
    if START in old and END in old:
        head, rest = old.split(START, 1)
        block, tail = rest.split(END, 1)
        return head + START + "\n" + keep_ticks(body, block) + "\n" + END + tail
    return ("# Compliance checklist\n\n" + START + "\n" + body + "\n" + END + "\n\n"
            "## Notes\n\nYours: anything here, outside the generated block, is kept.\n")  # fmt: skip


def cmd_checklist(a: argparse.Namespace) -> int:
    root = Path(a.app)
    brief, err = load_brief(root)
    if brief is None or not isinstance(brief.get("risk"), dict):
        print(f"risk checklist: {err or 'the idea was never screened (no risk block)'}: run "
              "the risk step of the App in a Box shape skill first")  # fmt: skip
        return 1
    out = root / (a.out or OUT)
    old = out.read_text(encoding="utf-8") if out.is_file() else ""
    new = render_checklist(root, brief["risk"], load_categories(a.categories), old)
    if a.check:
        if new != old:
            print(f"risk checklist: {out.relative_to(root)} is out of date with design/brief.json. "
                  "Run: python3 scripts/risk_gate.py checklist")  # fmt: skip
            return 1
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(new, encoding="utf-8")
    print(f"risk checklist: wrote {out.relative_to(root)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "open", "checklist", "rescreen"):
        s = sub.add_parser(name)
        s.add_argument("--app", default=".", help="the app's root (default: here)")
        s.add_argument("--categories", help="the kit's scripts/risk/categories.json")
        if name == "open":
            s.add_argument("--json", action="store_true")
        if name == "checklist":
            s.add_argument("--out", help=f"default {OUT}")
            s.add_argument("--check", action="store_true", help="fail if out of date")
        if name == "rescreen":
            s.add_argument("--text", help="the feature, in words (a spec, a ticket)")
            s.add_argument("--file", action="append", help="a file to screen (repeatable)")
            s.add_argument("--check", action="store_true", help="report only; exit 1 if new")
    a = p.parse_args(argv)
    return {"check": cmd_check, "open": cmd_open, "checklist": cmd_checklist,
            "rescreen": cmd_rescreen}[a.cmd](a)  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
