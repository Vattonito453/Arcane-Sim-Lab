#!/usr/bin/env python3
"""Score the neutral combat rubric emitted by shim >= 0.9.0.

The point of this scorer is comparability. Every earlier behavioural number we
had came from PlanPlayerController's own agent log, which stock Forge does not
emit at all, so "stock vs agent" was never measured on one scale. The shim's
RubricObserver reads the LIVE combat from the event bus for every seat
regardless of pilot, so the records below describe stock and plan seats
identically.

Pilot attribution comes from the meta record, whose `agents` and `players`
arrays are positionally aligned.

Metrics, all per pilot:

  block engagement   attackers blocked / attackers faced
  declined-legal     of attackers a legal blocker existed for, share let through
  free capture       of available kill-and-survive blocks, share taken
  safe capture       of available survive-the-block chances, share taken
  block mix          v3 kills+survives, v2 trade, v1 wall, v0 chump
  damage per combat  life actually taken from unblocked attackers
  commitment         attackers / (attackers + untapped bodies that COULD attack)
  retained defense   share of attacks that kept a body home at all, and the
                     share that kept one big enough to survive the biggest
                     untapped creature the table could swing back

Usage:
  python studies/behavior_rubric/observer.py <dir-or-file> [<dir-or-file> ...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def load(path: Path):
    """Yield (pilot, record) for every rubric record in one shim JSONL."""
    pilots: dict[str, str] = {}
    recs = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") == "meta":
                agents = r.get("agents") or []
                players = r.get("players") or []
                for name, agent in zip(players, agents):
                    pilots[name] = agent
            elif r.get("rec") == "rubric":
                recs.append(r)
    for r in recs:
        yield pilots.get(r.get("player"), "?"), r


def blank():
    return defaultdict(float)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    files: list[Path] = []
    for a in argv:
        p = Path(a)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.jsonl")))
        elif p.is_file():
            files.append(p)
    if not files:
        print("no .jsonl files found")
        return 2

    agg: dict[str, defaultdict] = defaultdict(blank)
    for f in files:
        for pilot, r in load(f):
            t = agg[pilot]
            if r["kind"] == "block":
                t["blockRecs"] += 1
                for k in ("incoming", "blocked", "v3", "v2", "v1", "v0",
                          "available", "freeTaken", "freeMissed",
                          "safeMissed", "legalMissed", "lifeTaken"):
                    t[k] += r.get(k, 0)
            else:
                t["atkRecs"] += 1
                for k in ("attackers", "attackPower", "defenders", "held",
                          "heldEligible", "heldPower", "heldTough",
                          "backBodies", "backPower", "backBiggest"):
                    t[k] += r.get(k, 0)
                if "heldEligible" not in r:
                    t["missingElig"] += 1
                if r.get("held", 0) > 0:
                    t["keptAny"] += 1
                if r.get("heldTough", 0) > r.get("backBiggest", 0):
                    t["keptEnough"] += 1

    print(f"files: {len(files)}")
    order = [p for p in ("plan", "stock") if p in agg] + \
            [p for p in sorted(agg) if p not in ("plan", "stock")]

    def pct(num, den):
        return f"{num / den:.1%}" if den else "  n/a"

    print()
    print("BLOCKING")
    hdr = f"{'pilot':8} {'recs':>6} {'faced':>6} {'blockd':>7} {'engage':>7} " \
          f"{'declined':>9} {'freeCap':>8} {'safeCap':>8} {'dmg/combat':>11}"
    print(hdr)
    for p in order:
        t = agg[p]
        if not t["blockRecs"]:
            continue
        # Of attackers a legal block existed for, the share let through. The
        # denominator is blocked + legalMissed, not `incoming`: an attacker
        # nothing could legally block is not a decision.
        declinable = t["blocked"] + t["legalMissed"]
        free_opp = t["freeTaken"] + t["freeMissed"]
        # A survive-the-block chance taken shows up as v3 or v1.
        safe_taken = t["v3"] + t["v1"]
        safe_opp = safe_taken + t["safeMissed"]
        print(f"{p:8} {int(t['blockRecs']):>6} {int(t['incoming']):>6} "
              f"{int(t['blocked']):>7} {pct(t['blocked'], t['incoming']):>7} "
              f"{pct(t['legalMissed'], declinable):>9} "
              f"{pct(t['freeTaken'], free_opp):>8} "
              f"{pct(safe_taken, safe_opp):>8} "
              f"{t['lifeTaken'] / t['blockRecs']:>11.2f}")

    print()
    print("BLOCK QUALITY MIX (share of blocks made)")
    print(f"{'pilot':8} {'blocks':>7} {'v3 kill+live':>13} {'v2 trade':>9} "
          f"{'v1 wall':>8} {'v0 chump':>9}")
    for p in order:
        t = agg[p]
        tot = t["v3"] + t["v2"] + t["v1"] + t["v0"]
        if not tot:
            continue
        print(f"{p:8} {int(tot):>7} {pct(t['v3'], tot):>13} "
              f"{pct(t['v2'], tot):>9} {pct(t['v1'], tot):>8} "
              f"{pct(t['v0'], tot):>9}")

    print()
    print("ATTACKING")
    print(f"{'pilot':8} {'recs':>6} {'atk/comb':>9} {'commit':>7} "
          f"{'spread':>7} {'keptAny':>8} {'keptEnough':>11}")
    for p in order:
        t = agg[p]
        if not t["atkRecs"]:
            continue
        # Eligible bodies only. `held` counts summoning-sick creatures and
        # creatures with defender, which were never able to attack, so using it
        # here understates commitment for both pilots.
        den = t["attackers"] + t["heldEligible"]
        # Records from shim < 0.9.1 carry no heldEligible. Reading them here
        # would silently make den == attackers and report commit = 100%, so
        # say so instead of printing a confident wrong number.
        if t["missingElig"]:
            commit_s = f"stale({int(t['missingElig'])})"
        else:
            commit_s = f"{t['attackers'] / den:.1%}" if den else "n/a"
        print(f"{p:8} {int(t['atkRecs']):>6} "
              f"{t['attackers'] / t['atkRecs']:>9.2f} {commit_s:>7} "
              f"{t['defenders'] / t['atkRecs']:>7.2f} "
              f"{pct(t['keptAny'], t['atkRecs']):>8} "
              f"{pct(t['keptEnough'], t['atkRecs']):>11}")

    print()
    print("keptAny = attacks that left any untapped body home; keptEnough = "
          "attacks that left\nenough toughness to survive the biggest untapped "
          "creature the rest of the table had.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
