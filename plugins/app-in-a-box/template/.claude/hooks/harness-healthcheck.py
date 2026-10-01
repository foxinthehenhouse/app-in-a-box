#!/usr/bin/env python3
"""INTEGRITY: drift detection for the self-learning harness.

A self-improving system's dangerous failure mode is silent degradation: so much
runs automatically that one broken piece rots everything downstream and nobody
notices (the classic: a capture hook that is on disk but never registered, so
the loop learns nothing for weeks). This makes drift LOUD.

Two modes:
  (default)   full report + exit code (0 healthy, 1 drift). Used by the
              `harness-check` skill. Includes slower cross-checks.
  --session   SessionStart hook: prints ONLY drift, overdue-ritual directives
              and notes, as plain text (works in Claude Code and Codex). Prints
              nothing when healthy. Always exits 0.

Existence is not function. Checks 1-2 verify components are on disk and wired;
the LIVENESS checks (capture flowing/converging, extractor sees transcripts)
test OUTPUT, because "0 corrections" is what a healthy loop and a disconnected
one both look like. Any sensor whose broken state resembles its healthy state
must be checked for connectivity, not just existence.

Ritual cadence replaces a scheduler: there is no cron here. Each SessionStart
compares state.json's last-run stamps against manifest `cadence` and escalates
(overdue -> run before substantive work -> run FIRST) until the ritual runs.
"""

import argparse
import collections
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_paths import (  # noqa: E402
    captures_dir,
    claude_transcript_dirs,
    codex_transcripts,
    load_state,
    orphan_capture_silos,
    pending_reflection_file,
    project_root,
    save_state,
)

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def days_since(iso):
    try:
        return (
            datetime.datetime.now() - datetime.datetime.fromisoformat(str(iso).replace("Z", ""))
        ).days
    except Exception:
        return None


def seed_age_days(path):
    """Age of the pending-reflection seed: header timestamp, else mtime."""
    try:
        head = open(path).read(400)
    except Exception:
        return None
    m = re.search(r"seeded by session-reflect\.sh at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC", head)
    if m:
        try:
            dt = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
            return (datetime.datetime.utcnow() - dt).days
        except Exception:
            pass
    try:
        return (
            datetime.datetime.now() - datetime.datetime.fromtimestamp(os.path.getmtime(path))
        ).days
    except Exception:
        return None


def run(name):
    """How to invoke a skill in either agent."""
    return f"the `{name}` skill (`/{name}` in Claude Code, `${name}` in Codex)"


def run_checks(root, deep=False):
    captures = captures_dir(root)
    mem = os.path.join(root, ".agents", "memory")
    checks, nudges, directives = [], [], []  # (ok, label, detail) / str / (sev, str)

    def add(ok, label, detail=""):
        checks.append((ok, label, detail))

    manifest = load_json(os.path.join(root, ".claude", "harness", "manifest.json")) or {}
    settings = load_json(os.path.join(root, ".claude", "settings.json")) or {}
    settings_blob = json.dumps(settings)
    state = load_state(root)
    if not state.get("installed"):
        # Anchor for "never run" cadence, so a fresh install doesn't nag on day zero.
        state["installed"] = datetime.datetime.now().isoformat(timespec="seconds")
        try:
            save_state(state, root)
        except Exception:
            pass

    # 1. Protected components exist on disk.
    for group, items in manifest.items():
        if group.startswith("protected_") and isinstance(items, list):
            for item in items:
                f = item.get("file") if isinstance(item, dict) else None
                if f:
                    add(os.path.exists(os.path.join(root, f)), f"exists: {f}")

    # 2. Required hooks are REGISTERED (drift = silent death).
    must = manifest.get("registered_hook_check", {}).get("must_be_registered", [])
    for name in must:
        ok = name in settings_blob
        add(ok, f"registered: {name}", "" if ok else "NOT wired in .claude/settings.json")
    # 2b. The Codex adapter is generated from settings.json; a stale one runs old hooks.
    codex_hooks = os.path.join(root, ".codex", "hooks.json")
    if os.path.exists(codex_hooks):
        try:
            blob = open(codex_hooks).read()
            missing = [n for n in must if n in settings_blob and n not in blob]
            if missing:
                nudges.append(
                    f".codex/hooks.json is missing {', '.join(missing)}: regenerate the "
                    "Codex adapters (see .agents/README.md), then re-trust the hooks in Codex."
                )
        except Exception:
            pass

    # 3. Capture is flowing.
    cad = manifest.get("cadence", {})
    stale_days = cad.get("capture_stale_days", 3)
    activity = sorted(glob.glob(os.path.join(captures, "*-activity.md")))
    if activity:
        age = (
            datetime.datetime.now()
            - datetime.datetime.fromtimestamp(os.path.getmtime(activity[-1]))
        ).days
        add(
            age <= stale_days,
            "capture flowing",
            "" if age <= stale_days else f"newest activity log is {age}d old (>{stale_days}d)",
        )
    else:
        add(True, "capture flowing", "no activity logs yet (new install)")

    # 3b. LIVENESS: capture CONVERGES to one directory across worktrees.
    silos = orphan_capture_silos(root)
    if silos:
        add(
            False,
            "capture converging",
            f"{len(silos)} per-worktree capture silo(s) that nothing reads: {', '.join(silos[:3])}. "
            "A writer is deriving its own path instead of harness_paths.captures_dir().",
        )
    else:
        add(True, "capture converging")

    # 3c. LIVENESS: the extractor can SEE transcripts. Counting files is cheap, so
    # it runs on the SessionStart path too.
    cutoff = time.time() - 14 * 86400
    claude_n = 0
    for d in claude_transcript_dirs(root):
        try:
            claude_n += sum(
                1
                for fn in os.listdir(d)
                if fn.endswith(".jsonl") and os.path.getmtime(os.path.join(d, fn)) >= cutoff
            )
        except Exception:
            continue
    codex_n = len(codex_transcripts(root, cutoff))
    visible = claude_n + codex_n
    if visible:
        add(True, "extractor sees transcripts", f"{claude_n} Claude + {codex_n} Codex in 14d")
    elif activity:
        # Sessions happened (capture logged them) yet no transcript is visible.
        add(
            False,
            "extractor sees transcripts",
            "0 transcripts in 14d although capture is logging sessions: the signal source is "
            "DISCONNECTED, and downstream it reads as '0 corrections'. Check "
            "`python3 .claude/hooks/harness_paths.py` and manifest `transcripts`.",
        )
    else:
        add(True, "extractor sees transcripts", "none yet (new install)")

    # 3d. Deep: the extractor resolves the SAME transcripts we just counted.
    if deep and visible:
        try:
            out = subprocess.run(
                [
                    sys.executable,
                    os.path.join(HOOK_DIR, "pattern-extractor.py"),
                    "--days",
                    "14",
                    "--output",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "CLAUDE_PROJECT_DIR": root},
            )
            n = json.loads(out.stdout or "{}").get("transcripts_scanned")
            add(
                n == visible,
                "extractor agrees with healthcheck",
                (
                    ""
                    if n == visible
                    else f"healthcheck sees {visible}, extractor sees {n}: "
                    "two path derivations have diverged"
                ),
            )
        except Exception as e:
            add(False, "extractor agrees with healthcheck", f"could not run extractor: {e}")

    # 4. Memory index intact and matching disk, both ways. A note missing from the
    # index is on disk and functionally invisible.
    memory_md = os.path.join(mem, "MEMORY.md")
    add(os.path.exists(memory_md), "memory index (.agents/memory/MEMORY.md)")
    mem_files = [
        f
        for f in glob.glob(os.path.join(mem, "*.md"))
        if os.path.basename(f) != "MEMORY.md" and not os.path.basename(f).startswith("_")
    ]
    if os.path.exists(memory_md):
        try:
            index_text = re.sub(
                r"`[^`]*`", "", open(memory_md).read()
            )  # ignore examples in code spans
        except Exception:
            index_text = ""
        linked = {os.path.basename(x) for x in re.findall(r"\]\(([^)]+\.md)\)", index_text)}
        on_disk = {os.path.basename(f) for f in mem_files}
        unindexed, phantom = sorted(on_disk - linked), sorted(linked - on_disk)
        if unindexed or phantom:
            bits = []
            if unindexed:
                bits.append(f"{len(unindexed)} on disk but NOT indexed: {', '.join(unindexed[:4])}")
            if phantom:
                bits.append(f"{len(phantom)} indexed but missing: {', '.join(phantom[:4])}")
            add(False, "memory index matches disk", " · ".join(bits) + f". Run {run('reflect')}.")
        else:
            add(True, "memory index matches disk", f"{len(on_disk)} note(s)")

    # 5. Memory cross-links: dangling [[links]] and orphans (nudges, not failures).
    alias, bodies = {}, {}
    for f in mem_files:
        s = os.path.basename(f)[:-3]
        try:
            bodies[s] = open(f).read()
        except Exception:
            bodies[s] = ""
        alias[s] = s
        for m in re.finditer(r"^(?:name|title):\s*(.+)$", bodies[s], re.M):
            alias[m.group(1).strip()] = s
    edges_in, edges_out, broken = collections.defaultdict(set), collections.defaultdict(set), []
    for s, body in bodies.items():
        for link in re.findall(r"\[\[([^\]]+)\]\]", body):
            t = alias.get(link.strip())
            if not t:
                broken.append((s, link.strip()))
            elif t != s:
                edges_out[s].add(t)
                edges_in[t].add(s)
    orphans = sorted(s for s in bodies if not edges_in[s] and not edges_out[s])
    if len(bodies) > 1 and orphans:
        nudges.append(
            f"{len(orphans)} orphan memory note(s) with no [[links]] in or out: "
            f"{', '.join(orphans[:4])}. Link them during reflect, or confirm they stand alone."
        )
    if broken:
        nudges.append(
            f"{len(broken)} dangling memory link(s): "
            + ", ".join(f"{a}->[[{b}]]" for a, b in broken[:4])
            + ". Write the target note or remove the link during reflect."
        )

    # 6. Ritual cadence: ESCALATING directives (soft -> firm at 2x -> top at 3x).
    last = state.get("last_run", {})
    install_age = days_since(state.get("installed"))
    seed = pending_reflection_file(root)

    def severity(age, limit):
        if age is None or age < limit:
            return 0
        return 3 if age >= 3 * limit else 2 if age >= 2 * limit else 1

    scheduled = set(cad.get("scheduled", []))  # run by a Routine/cron (routines skill)
    for ritual, key, default in (
        ("reflect", "reflect_days", 10),
        ("harness-optimize", "optimize_days", 7),
        ("north-star-report", "north_star_days", None),  # only when the cadence is set
    ):
        limit = cad.get(key, default)
        if limit is None or ritual in scheduled:
            continue
        ts = last.get(ritual)
        age = days_since(ts) if ts else install_age
        sev = severity(age, limit)
        reason = f"last ran {age}d ago" if ts else "has never run"
        if ritual == "north-star-report":
            sev = min(sev, 1)  # a product readout, not the self-learning loop: never escalate
        if ritual == "reflect":
            sa = seed_age_days(seed) if os.path.exists(seed) else None
            if sa is not None and sa >= limit and max(2, severity(sa, limit)) > sev:
                sev = max(2, severity(sa, limit))
                reason = f"has a {sa}d-old unconsumed reflection seed"
        if sev == 3:
            directives.append(
                (
                    3,
                    f"RUN {run(ritual)} NOW, before any other work: it {reason} "
                    f"(cadence {limit}d). The self-learning loop is stalled until it runs.",
                )
            )
        elif sev == 2:
            directives.append(
                (
                    2,
                    f"Run {run(ritual)} before substantive work: it {reason} "
                    f"(cadence {limit}d).",
                )
            )
        elif sev == 1:
            directives.append(
                (
                    1,
                    f"{run(ritual)} is overdue: it {reason} (cadence {limit}d). "
                    "Run it at a natural break.",
                )
            )

    # 6b. Complexity budget: an ACCRETION alarm, never a failure.
    limits = manifest.get("complexity_budget", {}).get("limits", {})
    if limits:
        try:
            agents_md = sum(1 for _ in open(os.path.join(root, "AGENTS.md")))
        except Exception:
            agents_md = 0
        actual = {
            "agents_md_lines": agents_md,
            "rules": len(
                [
                    f
                    for f in glob.glob(os.path.join(root, ".agents/rules/*.md"))
                    if os.path.basename(f) != "README.md"
                ]
            ),
            "registered_hooks": len(set(re.findall(r"hooks/([\w.-]+)", settings_blob))),
            "skills": len(glob.glob(os.path.join(root, ".agents/skills/*/SKILL.md"))),
            "agents": len(glob.glob(os.path.join(root, ".agents/agents/*.md"))),
            "memory_entries": len(mem_files),
        }
        over = [
            f"{k} {actual[k]}/{limits[k]}" for k in limits if k in actual and actual[k] > limits[k]
        ]
        if over:
            nudges.append(
                f"Complexity budget exceeded ({', '.join(over)}): {run('harness-optimize')} "
                "owes a pruning look (capability re-test + manifest sunset protocol). "
                "Protected components are exempt; memory is never auto-pruned."
            )

    # 6c. Soft spend budget: inert until manifest.spend_budget.weekly_ite is set.
    if (manifest.get("spend_budget") or {}).get("weekly_ite"):
        try:
            import importlib.util as ilu

            spec = ilu.spec_from_file_location(
                "spend_ledger", os.path.join(HOOK_DIR, "spend_ledger.py")
            )
            sl = ilu.module_from_spec(spec)
            spec.loader.exec_module(sl)
            msg = sl.weekly_budget_nudge(manifest, claude_transcript_dirs(root))
            if msg:
                nudges.append(msg)
        except Exception:
            pass

    # 6d. Hook RUNTIME failures. Registration can't see a hook that crashes on every
    # call; Claude Code records that only as a transcript attachment.
    try:
        horizon = (3 if deep else 1) * 86400
        files = []
        for d in claude_transcript_dirs(root):
            for fp in glob.glob(os.path.join(d, "*.jsonl")):
                try:
                    mt = os.path.getmtime(fp)
                except OSError:
                    continue
                if mt >= time.time() - horizon:
                    files.append((mt, fp))
        files.sort(reverse=True)
        if not deep:
            files = files[:8]
        errs = collections.Counter()
        for _, fp in files:
            with open(fp, "rb") as fh:
                if not deep:
                    fh.seek(max(0, os.path.getsize(fp) - 1_000_000))
                for ln in fh:
                    if b"hook_non_blocking_error" not in ln:
                        continue
                    try:
                        att = json.loads(ln).get("attachment") or {}
                    except Exception:
                        continue
                    blob = " ".join(
                        str(att.get(k) or "") for k in ("command", "hookName", "stderr")
                    )
                    m = re.search(r"hooks/([\w.-]+)", blob)
                    errs[
                        f"{m.group(1) if m else att.get('hookName', '?')} (exit {att.get('exitCode')})"
                    ] += 1
        if errs:
            msg = (
                f"{sum(errs.values())} hook runtime error(s) in {horizon // 86400}d: "
                + ", ".join(f"{k} x{n}" for k, n in errs.most_common(4))
                + ". A hook that errors is silently OFF. Details: "
                "`python3 .claude/hooks/pattern-extractor.py --output text`."
            )
            add(False, "hooks ran without runtime errors", msg) if deep else nudges.append(msg)
        elif deep:
            add(True, "hooks ran without runtime errors", f"{len(files)} transcript(s), 3d")
    except Exception:
        pass

    # 6e. Components nobody uses (60d of capture history required). An unused
    # skill still costs its description in every session's listing budget.
    try:
        window = 60
        acts = sorted(glob.glob(os.path.join(captures, "*-activity.md")))
        if (
            acts
            and days_since(os.path.basename(acts[0])[:10]) is not None
            and days_since(os.path.basename(acts[0])[:10]) >= window
        ):
            since = (datetime.date.today() - datetime.timedelta(days=window)).isoformat()
            used = set()
            for fp in acts:
                if os.path.basename(fp)[:10] < since:
                    continue
                for ln in open(fp, errors="replace"):
                    for m in re.finditer(r"(?:Skill|Slash) /([\w:.-]+)|Agent\[([\w:.-]+)\]", ln):
                        used.add((m.group(1) or m.group(2)).split(":")[-1])
            protected = set()
            for g, items in manifest.items():
                if g.startswith("protected_") and isinstance(items, list):
                    for i in items:
                        f = i.get("file", "") if isinstance(i, dict) else ""
                        protected.add(
                            os.path.basename(os.path.dirname(f))
                            if f.endswith("SKILL.md")
                            else os.path.basename(f)[:-3]
                        )
            skills = [
                os.path.basename(os.path.dirname(p))
                for p in glob.glob(os.path.join(root, ".agents/skills/*/SKILL.md"))
            ]
            agents = [
                os.path.basename(p)[:-3]
                for p in glob.glob(os.path.join(root, ".agents/agents/*.md"))
            ]
            un_sk = sorted(s for s in skills if s not in used and s not in protected)
            un_ag = sorted(a for a in agents if a not in used and a not in protected)
            if un_sk or un_ag:
                nudges.append(
                    f"{len(un_sk)} skill(s) and {len(un_ag)} agent(s) unused in {window}d "
                    f"(skills: {', '.join(un_sk[:6]) or '-'}; agents: {', '.join(un_ag[:6]) or '-'}). "
                    f"{run('harness-optimize')} owes each a capability re-test, or a sharper "
                    "description if it SHOULD have fired."
                )
    except Exception:
        pass

    # 6f. Deep only (network): CI workflows whose latest run failed.
    if deep:
        try:
            r = subprocess.run(
                ["gh", "run", "list", "--limit", "100", "--json", "workflowName,conclusion,status"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=20,
            )
            latest = {}
            for wf in json.loads(r.stdout or "[]"):
                if wf.get("status") != "completed" or wf.get("conclusion") in (
                    "skipped",
                    "cancelled",
                ):
                    continue
                latest.setdefault(wf["workflowName"], wf["conclusion"])
            red = sorted(w for w, c in latest.items() if c != "success")
            add(
                not red,
                "CI workflows: latest run of each is green",
                ("latest run FAILED: " + ", ".join(red)) if red else f"{len(latest)} workflow(s)",
            )
        except Exception as e:
            add(
                True,
                "CI workflows: latest run of each is green",
                f"not checked ({type(e).__name__})",
            )

    # 7. Pending reflection seed. Suppressed the same day reflect ran, since the Stop
    # hook re-seeds after every turn and a nudge that is always true teaches people
    # to scroll past nudges.
    if os.path.exists(seed):
        sa = seed_age_days(seed)
        if not (sa == 0 and days_since(last.get("reflect")) == 0):
            nudges.append(
                f"A pending-reflection seed is waiting ({sa}d old): {seed}. "
                f"Consume it with {run('reflect')}, or delete it if nothing's worth keeping."
            )

    return checks, nudges, directives


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", action="store_true")
    args = ap.parse_args()
    if args.session:
        try:
            sys.stdin.close()  # the hook payload is unused; never block reading it
        except Exception:
            pass
    root = project_root()
    try:
        checks, nudges, directives = run_checks(root, deep=not args.session)
    except Exception as e:
        if args.session:
            return 0  # fail open: a broken sensor must never break session start
        print(f"healthcheck crashed: {e}")
        return 1
    failures = [c for c in checks if not c[0]]
    directives.sort(key=lambda d: -d[0])
    top = directives[0][0] if directives else 0

    if args.session:
        if not failures and not directives and not nudges:
            return 0
        lines = []
        if top >= 3:
            lines.append("### SELF-LEARNING LOOP STALLED: ACTION REQUIRED FIRST")
            lines += [f"- {t}" for _, t in directives]
        if failures:
            lines.append("### Harness drift detected")
            lines += [
                f"- FAIL: {label}" + (f": {detail}" if detail else "")
                for _, label, detail in failures
            ]
            lines.append(f"Run {run('harness-check')} for the full report.")
        if directives and top < 3:
            lines.append(
                "### Harness cadence" + (": run before substantive work" if top == 2 else "")
            )
            lines += [f"- {t}" for _, t in directives]
        if nudges:
            lines.append("### Harness notes")
            lines += [f"- {n}" for n in nudges]
        print("\n".join(lines))
        return 0

    print("# Harness healthcheck\n")
    for ok, label, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail else ""))
    if directives:
        print("\n## Ritual cadence (escalating)")
        for sev, text in directives:
            print(f"  - [{ {1: 'OVERDUE', 2: 'WELL OVERDUE', 3: 'TOP PRIORITY'}[sev] }] {text}")
    if nudges:
        print("\n## Notes")
        for n in nudges:
            print(f"  - {n}")
    if failures:
        print(f"\nDRIFT DETECTED: {len(failures)} check(s) failed.")
        return 1
    print(f"\nAll {len(checks)} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
