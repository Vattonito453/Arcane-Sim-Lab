#!/usr/bin/env python3
"""A/B: the 0.16.0 "new engine" (SeeCombat solver + priority gates) against
the 0.15.0 agent, paired within a game.

Design.
  MIXED PODS, BOTH PILOTS ARE PLAN AGENTS. Every game seats two NEW seats and
  two BASE seats, alternating. Both run the same shim jar; the only
  difference is the plan personality each deck is handed for that game
  (combatSolver / priorityGates 1.0 for NEW, 0.0 for BASE, which is exactly
  the 0.15.0 agent). Same shuffle, same opponents, same board: the win-share
  comparison is paired, null 50%.
  EVERY DECK PLAYS BOTH SIDES. Four rotations per pod rotate the seat order;
  the pod's even-indexed decks are NEW in rotations 0 and 1 and BASE in 2
  and 3, odd-indexed decks the reverse, so each deck is NEW twice and BASE
  twice, sits in every seat once, and no deck's strength leaks into the
  pilot comparison.
  PODS. Pod 0 is the four bundled decks (the pod the 0.15.0 acceptance was
  measured on); the rest are seeded precon pods from the prediction cohort,
  the same shuffle studies/behavior_rubric/run_arms.py uses.
  CENSORING. 1200 s clock plus the 120-turn cap. Both pilots sit in every
  game, so a killed game drops NEW and BASE data symmetrically.

Usage:
  python studies/engine_ab/run_ab.py --pods 16 --games 1 --workers 14
  python studies/engine_ab/run_ab.py --report            # tally what exists
  python studies/engine_ab/run_ab.py --mode allnew --games 4
      # bundled pod, all four seats NEW, seat-rotated: the divergence arm,
      # compared against the 0.15.0 humanized pod (task21_v015h)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "engine"))

SHIM = REPO.parent / "simlab-forge-shim" / "simlab-forge-shim-0.16.0.jar"
FORGE = Path(os.path.expanduser("~/forge/forge-gui-desktop-2.0.13-jar-with-dependencies.jar"))
SEED = 20260827
NEW = {"combatSolver": 1.0, "priorityGates": 1.0}
BASE = {"combatSolver": 0.0, "priorityGates": 0.0}
BUNDLED = ["atraxa_counters.dck", "drana_vampires.dck", "nekusar_punisher.dck", "kambal_taxes.dck"]
SEAT_RE = re.compile(r"^Ai\((\d+)\)-")


def make_pods(n_pods: int) -> list[list[str]]:
    pods = [[str(REPO / "engine" / "decks" / d) for d in BUNDLED]]
    cohort = json.loads((REPO / "studies/precon_predict/cohort.json").read_text(encoding="utf-8"))
    files = [d["file"] for d in cohort if Path(d["file"]).is_file()]
    rng = random.Random(SEED)
    rng.shuffle(files)
    pods += [files[i:i + 4] for i in range(0, len(files) - 3, 4)]
    return pods[:n_pods]


def build_plans_cached(decks: list[str], out: Path) -> dict:
    from deck_plan import build_plans
    if out.exists() and out.stat().st_size > 0:
        return json.loads(out.read_text(encoding="utf-8"))
    plans = build_plans(decks)
    bad = [f"{n} cov={p.get('factsCoverage', 0):.2f}" for n, p in plans["decks"].items()
           if p.get("factsCoverage", 0) < 0.9]
    if bad:
        sys.exit("degraded plan data, refusing to run: " + "; ".join(bad[:5]))
    out.write_text(json.dumps(plans, indent=1), encoding="utf-8")
    return plans


def deck_name(plans: dict, deck_file: str) -> str:
    """Plans are keyed by the deck's Forge name; map a file to it via the
    order build_plans preserved, falling back to the [metadata] Name line."""
    text = Path(deck_file).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^Name=(.*)$", text, re.M)
    if m and m.group(1).strip() in plans["decks"]:
        return m.group(1).strip()
    for n in plans["decks"]:
        if Path(deck_file).stem.replace("_", " ").lower() in n.lower():
            return n
    sys.exit(f"cannot map {deck_file} to a plan name")


def finished(out: Path) -> bool:
    if not out.exists() or out.stat().st_size < 1000:
        return False
    try:
        with out.open(encoding="utf-8", errors="replace") as fh:
            return any('"rec":"result"' in line for line in fh)
    except OSError:
        return False


def cell(spec) -> str:
    mode, pod_i, rot, decks, base_plans, out, games, clock = spec
    if finished(out):
        return f"pod{pod_i} rot{rot} cached"
    order = decks[rot:] + decks[:rot]
    # Seat i holds pod deck (i + rot) % 4. Even-indexed decks are NEW in
    # rotations 0 and 1 and BASE in 2 and 3; odd-indexed decks the reverse.
    # (The first cut flipped the parity on odd rotations, which the seat
    # rotation exactly cancels, so every deck sat on one side all four
    # times; measured as zero decks with games on both sides.)
    plans = json.loads(json.dumps(base_plans))
    sides = []
    for seat, deck in enumerate(order):
        j = (seat + rot) % 4
        new = (mode == "allnew") or ((j % 2 == 0) != (rot >= 2))
        plans["decks"][deck_name(plans, deck)].setdefault("personality", {}).update(NEW if new else BASE)
        sides.append("NEW" if new else "BASE")
    plans_path = out.with_suffix(".plans.json")
    plans_path.write_text(json.dumps(plans), encoding="utf-8")
    cmd = ["java", "-Xmx3g", "-cp", f"{SHIM}{os.pathsep}{FORGE}",
           "simlab.shim.SimShim", "--decks", *order,
           "--games", str(games), "--timeout", str(clock), "--max-turns", "120",
           "--plans", str(plans_path.resolve()),
           "--seat-pilots", ",".join(["plan:SimLabHuman"] * 4),
           "--out", str(out.resolve())]
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        subprocess.run(cmd, cwd=os.path.expanduser("~/forge"),
                       stdout=subprocess.DEVNULL, stderr=eh, check=False)
    out.with_suffix(".sides.json").write_text(json.dumps(sides), encoding="utf-8")
    return f"pod{pod_i} rot{rot} {'ok' if finished(out) else 'FAILED'}"


def report(root: Path) -> int:
    """NEW vs BASE win share on decided games, paired within game."""
    wins = Counter()
    played = decided = 0
    by_pod = defaultdict(lambda: Counter())
    events = defaultdict(Counter)
    durations = []
    for f in sorted(root.glob("pod*_rot*.jsonl")):
        sides_f = f.with_suffix(".sides.json")
        if not sides_f.exists():
            continue
        sides = json.loads(sides_f.read_text(encoding="utf-8"))
        m = re.match(r"pod(\d+)_rot(\d+)", f.name)
        pod = m.group(1)
        seat_side = {}
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"rec":"meta"' in line:
                meta = json.loads(line)
                for i, p in enumerate(meta.get("players", [])):
                    seat_side[p] = sides[i]
            elif '"rec":"result"' in line:
                r = json.loads(line)
                played += 1
                durations.append(r.get("ms", 0) / 1000)
                w = r.get("winner")
                if r.get("draw") or not w or r.get("timedOut"):
                    continue
                mm = SEAT_RE.match(w)
                if not mm:
                    continue
                side = sides[int(mm.group(1)) - 1]
                decided += 1
                wins[side] += 1
                by_pod[pod][side] += 1
            elif '"rec":"agent"' in line:
                r = json.loads(line)
                side = seat_side.get(r.get("player"))
                if side:
                    events[side][r.get("event")] += 1
    print(f"games played {played}, decided {decided}, censored {played - decided}")
    if decided:
        share = wins["NEW"] / decided
        se = (share * (1 - share) / decided) ** 0.5
        print(f"NEW wins {wins['NEW']}, BASE wins {wins['BASE']}: "
              f"NEW share {share:.1%} +/- {se * 100:.1f} pp (1 SE), null 50%, "
              f"95% CI [{share - 1.96 * se:.1%}, {share + 1.96 * se:.1%}]")
        z = (share - 0.5) / (0.25 / decided) ** 0.5
        print(f"z vs 50%: {z:+.2f}")
    if durations:
        durations.sort()
        print(f"game seconds: median {durations[len(durations) // 2]:.0f}, "
              f"p90 {durations[int(0.9 * len(durations)) - 1]:.0f}")
    for pod in sorted(by_pod, key=int):
        c = by_pod[pod]
        n = c["NEW"] + c["BASE"]
        print(f"  pod{pod}: NEW {c['NEW']}/{n}" + ("  (bundled decks)" if pod == "0" else ""))
    for side in ("NEW", "BASE"):
        keys = ["see_attack", "see_block", "see_damage", "instant_hold", "instant_window",
                "protect_hold", "protect_window", "added_block", "hold_back", "block_skip",
                "counter_fire", "counter_veto", "see_error", "block_error"]
        print(f"  {side} events: " + ", ".join(f"{k}={events[side][k]}" for k in keys if events[side][k]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ab", "allnew"], default="ab")
    ap.add_argument("--pods", type=int, default=16)
    ap.add_argument("--games", type=int, default=1, help="games per invocation")
    ap.add_argument("--clock", type=int, default=1200)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    root = HERE / ("runs_allnew" if args.mode == "allnew" else "runs")
    root.mkdir(parents=True, exist_ok=True)
    if args.report:
        return report(root)
    if not SHIM.is_file():
        sys.exit(f"shim jar not found: {SHIM}")
    pods = make_pods(1 if args.mode == "allnew" else args.pods)
    specs = []
    for i, decks in enumerate(pods):
        base_plans = build_plans_cached(decks, root / f"plans_pod{i}.json")
        for rot in range(4):
            specs.append((args.mode, i, rot, decks, base_plans,
                          root / f"pod{i}_rot{rot}.jsonl", args.games, args.clock))
    print(f"{len(pods)} pods x 4 rotations x {args.games} games = "
          f"{len(specs) * args.games} games, {args.workers} at a time, mode {args.mode}", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(cell, s) for s in specs]
        for f in as_completed(futs):
            done += 1
            print(f"[{done}/{len(specs)}] {f.result()}", flush=True)
    return report(root)


if __name__ == "__main__":
    raise SystemExit(main())
