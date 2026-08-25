#!/usr/bin/env python3
"""Task 20 Stage 2 acceptance checks over shim >= 0.5.0 raw JSONL.

Stage 0 and Stage 1 measured what a ranking WOULD have picked; Stage 2 makes
it act, so the questions change from "how often would it differ" to "did it
only act where it was allowed to". Each check prints its counts and a
verdict; an unproven check (the situation never arose) is reported as
UNPROVEN, never as a pass.

Checks:
  1. every steer is legal under the Stage 2 rules
       plan steers: mode=targets, value >= 2, value > stockValue, and the
       steered card is the paired search_seen's planPick
       combo steers: the steered card is that search's `missing` piece
  2. combo priority: whenever a line was sighted and its missing piece was in
     the options, the steer is mode=combo — including the subset where the
     plan ranking wanted something else and outranked stock (planW > pickedW
     and planPick != missing). That subset must be non-empty to count as
     proven.
  3. declines stand: no plan steer carries over=nothing
  4. inert arm (--inert): no plan steers at all, every search_seen mode=weights

Events are paired on sid, which shim 0.5.0 emits precisely because a turn can
resolve several searches.

Usage:
  python3 studies/tutor_targeting/analyze_stage2.py <shim_raw_*.jsonl ...> [--inert]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

SEEN = re.compile(
    r"sid=(?P<sid>\d+) options=(?P<options>\d+) sighted=(?P<sighted>\w+)"
    r" mode=(?P<mode>\w+) ranked=(?P<ranked>\d+) agree=(?P<agree>\w+)"
    r" pickedW=(?P<pickedw>\d+) planW=(?P<planw>\d+) dest=(?P<dest>\S*)"
    r" comboPick=(?P<combopick>\S*)"
    r" missing=(?P<missing>.*?) picked=(?P<picked>.*?)"
    r" planPick=(?P<planpick>.*?) src=(?P<src>.*)$"
)
STEER = re.compile(
    r"sid=(?P<sid>\d+) mode=(?P<mode>\w+) value=(?P<value>\d+)"
    r" stockValue=(?P<stockvalue>\d+) steer=(?P<steer>.*?) over=(?P<over>.*)$"
)


def main(argv: list[str]) -> int:
    inert = "--inert" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2

    seen: dict[tuple, dict] = {}
    steers: list[tuple[tuple, dict, dict]] = []
    unparsed = {"seen": 0, "steer": 0}
    versions: set[str] = set()
    orphans = 0

    for path in paths:
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("rec") == "meta":
                versions.add(str(rec.get("shim")))
                continue
            if rec.get("rec") != "agent":
                continue
            ev, detail = rec.get("event"), rec.get("detail", "")
            key_base = (path, rec.get("game"), rec.get("player"))
            if ev == "search_seen":
                m = SEEN.search(detail)
                if not m:
                    unparsed["seen"] += 1
                    continue
                seen[key_base + (m.group("sid"),)] = m.groupdict()
            elif ev == "tutor_steer":
                m = STEER.search(detail)
                if not m:
                    unparsed["steer"] += 1
                    continue
                k = key_base + (m.group("sid"),)
                if k not in seen:
                    orphans += 1
                    continue
                steers.append((k, m.groupdict(), seen[k]))

    print(f"shim versions seen: {sorted(versions) or ['?']}")
    print(f"searches: {len(seen)}   steers: {len(steers)}   "
          f"unparsed: {unparsed}   orphan steers: {orphans}")
    if unparsed["seen"] or unparsed["steer"] or orphans:
        print("  WARNING: unparsed or unpairable events. On shim < 0.5.0 that "
              "is expected (no sid); on 0.5.0 it is a bug.")

    by_mode: dict[str, int] = defaultdict(int)
    for _, s, _ in steers:
        by_mode[s["mode"]] += 1
    print(f"steer modes: {dict(by_mode)}")
    dests: dict[str, int] = defaultdict(int)
    for v in seen.values():
        dests[v["dest"]] += 1
    print(f"search destinations: {dict(dests)}")

    failures: list[str] = []
    unproven: list[str] = []

    # 1. every steer legal
    bad = []
    for k, s, sn in steers:
        if s["mode"] == "plan":
            if sn["mode"] != "targets":
                bad.append(f"{k}: plan steer in mode={sn['mode']}")
            if int(s["value"]) < 2:
                bad.append(f"{k}: plan steer value={s['value']} below floor")
            if int(s["value"]) <= int(s["stockvalue"]):
                bad.append(f"{k}: plan steer not strictly better "
                           f"({s['value']} vs {s['stockvalue']})")
            if s["steer"] != sn["planpick"]:
                bad.append(f"{k}: steered {s['steer']!r} != planPick "
                           f"{sn['planpick']!r}")
        elif s["mode"] == "combo":
            if sn["missing"] not in ("-", s["steer"]):
                bad.append(f"{k}: combo steered {s['steer']!r} != missing "
                           f"{sn['missing']!r}")
    print(f"\n[1] steer legality: {len(steers) - len(bad)}/{len(steers)} clean")
    for b in bad[:20]:
        print("    FAIL " + b)
    if bad:
        failures.append("steer legality")
    elif not steers:
        unproven.append("steer legality (no steer fired)")

    # 2. combo priority, including the contested subset.
    #    "Contested" needs comboPick=yes, not merely a sighted line: a line is
    #    usually sighted while the piece it needs is not among the options
    #    (Finale of Devastation offers creatures; the missing piece is an
    #    artifact). Those are not combo losing to plan, they are combo having
    #    nothing to take, and counting them as failures is how this check
    #    cried wolf on its first run.
    contested = 0
    contested_bad = 0
    unavailable = 0
    for k, s, sn in steers:
        if sn["sighted"] != "true" or sn["missing"] == "-":
            continue
        if sn.get("combopick") != "yes":
            unavailable += 1
            continue
        if sn["planpick"] not in ("-", sn["missing"]) and \
                int(sn["planw"]) > int(sn["pickedw"]):
            contested += 1
            if s["mode"] != "combo":
                contested_bad += 1
                print(f"    FAIL {k}: plan beat combo on a sighted line")
    print(f"[2] combo priority on contested searches: {contested} contested, "
          f"{contested_bad} lost ({unavailable} sighted searches did not offer "
          f"the missing piece)")
    if contested_bad:
        failures.append("combo priority")
    elif contested == 0:
        unproven.append("combo priority (no search had a sighted line AND a "
                        "different plan pick outranking stock)")

    # 3. declines stand
    forced = [k for k, s, _ in steers if s["mode"] == "plan" and s["over"] == "nothing"]
    print(f"[3] plan steers over a stock decline: {len(forced)} (must be 0)")
    if forced:
        failures.append("declines stand")

    # 4. inert arm
    if inert:
        plan_steers = [k for k, s, _ in steers if s["mode"] == "plan"]
        weights_only = all(v["mode"] == "weights" for v in seen.values())
        print(f"[4] inert arm: {len(plan_steers)} plan steers (must be 0); "
              f"all searches mode=weights: {weights_only}")
        if plan_steers or not weights_only:
            failures.append("inert arm")

    print()
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    if unproven:
        for u in unproven:
            print("UNPROVEN: " + u)
        print("No check failed, but the run did not exercise everything above.")
        return 0
    print("ALL STAGE 2 CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
