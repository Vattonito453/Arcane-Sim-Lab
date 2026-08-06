#!/usr/bin/env python3
"""Heterogeneous-pod follow-up to the mirror head-to-head.

The mirror run (RESULTS.md) answered strength in a SYMMETRIC matchup: four
copies of one decklist. That is not how Commander is played, and it is the most
substantive limitation named in PLAN.md section 3 - an agent could plausibly be
better at piloting DIVERSE pods in ways a mirror cannot show. This runs the same
2x2 arms in pods of four DIFFERENT decks.

    A  plan  + SimLabHuman   what ships today
    B  stock + Default       stock Forge
    C  stock + SimLabHuman   floodgate without the gate
    D  plan  + Default       our policy without the floodgate

The mirror got deck strength cancellation for free. Here it has to be designed
in, and three factors need balancing at once: deck, arm and seat. That needs two
orthogonal Latin squares (a Graeco-Latin square) of order 4, built over GF(4)
because 4 is not prime:

    deck index = r XOR s
    arm index  = r XOR (2 * s in GF(4)),  where 2*s = [0, 2, 3, 1]

Across the four rotations that gives, all simultaneously:
  - every deck exactly once per pod, and every arm exactly once per pod
  - every arm in every seat exactly once  -> cancels Forge's seat bias, measured
    at seat 1 ~11% vs seat 4 ~36% (run_sim.py:308)
  - every deck in every seat exactly once
  - every (deck, arm) pair exactly once   -> cancels deck strength

Balance is asserted at startup, and analyze_h2h.py re-checks it from the
recorded rows rather than trusting this file.

Usage:
    python3 studies/skill_headtohead/run_hetero.py --games 96 --workers 16
    python3 studies/skill_headtohead/run_hetero.py --dry-run
"""

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_h2h import (  # noqa: E402  reuse rather than fork the validated runner
    ARMS,
    ARM_ORDER,
    CORRELATION,
    ENGINE,
    find_forge_jar,
    forge_precons_dir,
    parse_cell,
    slugify,
)

# Two groups of four, each spanning the human ground-truth range and mixing
# archetypes, so a group is not secretly a difficulty tier. Deck strength
# cancels by design anyway; the grouping is for coverage.
#
# Tricky Terrain is included deliberately even though a 4-way MIRROR of it
# censored 94/96 games (RESULTS.md). One copy in a pod of four is a different
# game state, and whether the stall survives dilution is itself worth knowing.
# If group 2 stalls, group 1 is unaffected and still answers the question.
GROUPS = [
    ["Planeswalker Party",      # 40.87% human, planeswalkers
     "Explorers of the Deep",   # 25.25%, merfolk tribal
     "Mutant Menace",           # 15.12%, creatures
     "Deadly Disguise"],        # 11.96%, disguise/cloak
    ["Tricky Terrain",          # 32.07%, lands and counters
     "Doom Prevails",           # 21.06%, villain creatures
     "Blight Curse",            # 18.49%, curses
     "Grand Larceny"],          # 13.20%, theft/artifacts
]

# Multiplication by the primitive element in GF(4). Addition in GF(4) is XOR.
GF4_TIMES_TWO = [0, 2, 3, 1]


def square(rot, seat):
    """(deck index, arm index) for a seat in a rotation. See module docstring."""
    return rot ^ seat, rot ^ GF4_TIMES_TWO[seat]


def check_square():
    """Prove the design balances all three factors before spending any compute.

    A silently unbalanced square would leave seat bias or deck strength
    uncancelled, and every arm comparison downstream would be worthless.
    """
    pairs, arm_seat, deck_seat = set(), set(), set()
    for r in range(4):
        decks_in_pod, arms_in_pod = set(), set()
        for s in range(4):
            d, a = square(r, s)
            pairs.add((d, a))
            arm_seat.add((a, s))
            deck_seat.add((d, s))
            decks_in_pod.add(d)
            arms_in_pod.add(a)
        assert decks_in_pod == {0, 1, 2, 3}, f"rotation {r} repeats a deck"
        assert arms_in_pod == {0, 1, 2, 3}, f"rotation {r} repeats an arm"
    assert len(pairs) == 16, f"deck/arm pairs not orthogonal: {len(pairs)}/16"
    assert len(arm_seat) == 16, "arms not balanced across seats"
    assert len(deck_seat) == 16, "decks not balanced across seats"


def load_group(names):
    manifest = json.loads((CORRELATION / "manifest.json").read_text(encoding="utf-8"))
    by_name = {p["name"]: p for p in manifest["precons"]}
    missing = [n for n in names if n not in by_name]
    if missing:
        sys.exit(f"not in manifest: {missing}")
    return [by_name[n] for n in names]


def build_group_plans(deck_paths, out_path):
    """One plans file per group covering all four decks.

    Every deck needs a plan available because the rotation puts each of them on
    a plan seat once. A deck sitting on a STOCK seat simply has its plan ignored:
    --seat-pilots decides the pilot, not the presence of a plan.
    """
    sys.path.insert(0, str(ENGINE))
    from deck_plan import build_plans
    plans = build_plans([str(p) for p in deck_paths])
    out_path.write_text(json.dumps(plans, indent=2), encoding="utf-8")
    return list(plans["decks"].keys())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=96,
                    help="games per (group, rotation), split into chunks")
    ap.add_argument("--games-per-cell", type=int, default=8)
    ap.add_argument("--clock", type=int, default=1260)
    ap.add_argument("--heap", default="3g")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--groups", type=int, nargs="+", default=None,
                    help="which group indices to run (default: all)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--shim-jar", default=None)
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    check_square()

    if args.games % args.games_per_cell:
        sys.exit(f"--games {args.games} must be divisible by "
                 f"--games-per-cell {args.games_per_cell}")
    chunks = args.games // args.games_per_cell

    group_ids = args.groups if args.groups is not None else list(range(len(GROUPS)))
    for g in group_ids:
        if g < 0 or g >= len(GROUPS):
            sys.exit(f"group {g} out of range (0..{len(GROUPS) - 1})")

    out_dir = Path(args.out) if args.out else HERE / "runs_hetero"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    done = set()
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["group"], r["rotation"], r["chunk"],
                          r["games_requested"], r["clock"]))

    forge_jar = find_forge_jar()
    precons = forge_precons_dir()
    if not precons.is_dir():
        sys.exit(f"Forge precons not found: {precons}. Set FORGE_PRECONS.")

    pinned = Path(args.shim_jar) if args.shim_jar else HERE / "pinned" / "simlab-forge-shim.jar"
    if not pinned.is_file():
        sys.exit(f"pinned shim jar missing: {pinned}")
    shim_sha = hashlib.sha256(pinned.read_bytes()).hexdigest()[:16]

    groups = {g: load_group(GROUPS[g]) for g in group_ids}

    cells = [(g, rot, ch) for g in group_ids for rot in range(4) for ch in range(chunks)]
    todo = [c for c in cells
            if (c[0], c[1], c[2], args.games, args.clock) not in done]

    total_games = len(group_ids) * 4 * args.games
    print(f"shim      {pinned} (sha256 {shim_sha})")
    print(f"design    Graeco-Latin order 4: deck=r^s, arm=r^gf4(2s). Balanced.")
    print(f"groups    {len(group_ids)} x 4 rotations x {chunks} chunks "
          f"= {len(cells)} cells of {args.games_per_cell} games")
    print(f"          {total_games} games total, clock {args.clock}s")
    print(f"already done {len(cells) - len(todo)}, to run {len(todo)}")
    # 517 s/game measured on natural completions in the 2x2 MIRROR pod. A
    # heterogeneous pod may well be faster (a mirror of one deck can grind), so
    # treat this as an upper estimate rather than a floor.
    est_h = len(todo) * args.games_per_cell * 517 / 3600.0
    print(f"estimate  {est_h:.1f} h serial / {est_h / max(1, args.workers):.1f} h "
          f"at {args.workers} workers, at the mirror's 517 s/game")
    if args.dry_run:
        for g in group_ids:
            print(f"\n  group {g}:")
            for rot in range(4):
                seats = []
                for s in range(4):
                    di, ai = square(rot, s)
                    seats.append(f"s{s + 1}={ARM_ORDER[ai]}:{groups[g][di]['name'][:18]}")
                print(f"    rot{rot}  " + "  ".join(seats))
        return

    plans_dir = out_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plans_for = {}
    for g in group_ids:
        pf = plans_dir / f"plans_group{g}.json"
        if not pf.exists():
            paths = []
            for p in groups[g]:
                src = precons / p["forge_file"]
                if not src.is_file():
                    sys.exit(f"deck not found: {src}")
                paths.append(src)
            keys = build_group_plans(paths, pf)
            print(f"plans     group {g} -> {len(keys)} decks")
        plans_for[g] = pf

    slots = queue.Queue()
    for w in range(max(1, args.workers)):
        d = out_dir / "workers" / f"w{w}"
        (d / "decks" / "commander").mkdir(parents=True, exist_ok=True)
        slots.put(d)

    write_lock = threading.Lock()
    counter = {"n": 0}
    t_start = time.time()

    def run_cell(cell):
        g, rot, ch = cell
        worker = slots.get()
        try:
            group = groups[g]
            # Seat s gets deck square(rot,s)[0] piloted by arm square(rot,s)[1].
            seat_decks, seat_arms, staged, specs = {}, {}, [], []
            for s in range(4):
                di, ai = square(rot, s)
                p = group[di]
                arm = ARM_ORDER[ai]
                seat_decks[s + 1] = p["name"]
                seat_arms[s + 1] = arm
                specs.append(ARMS[arm])
                # Stage per seat: the same deck can be requested by different
                # workers concurrently, so the copy is worker-local.
                dst = worker / f"s{s + 1}_{slugify(p['name'])}.dck"
                shutil.copy2(precons / p["forge_file"], dst)
                staged.append(str(dst))

            run_id = (f"hetero_g{g}_rot{rot}_c{ch}_"
                      f"g{args.games_per_cell}_t{args.clock}")
            raw = out_dir / f"shim_raw_{run_id}.jsonl"
            cmd = ["java", f"-Xmx{args.heap}",
                   "-cp", f"{pinned}{os.pathsep}{forge_jar}",
                   "simlab.shim.SimShim",
                   "--decks", *staged,
                   "--plans", str(plans_for[g]),
                   "--seat-pilots", ",".join(specs),
                   "--games", str(args.games_per_cell),
                   "--timeout", str(args.clock),
                   "--out", str(raw)]
            t0 = time.time()
            proc = subprocess.run(
                cmd, cwd=str(forge_jar.parent),
                env={**os.environ, "FORGE_USER_DIR": str(worker)},
                capture_output=True, text=True)
            elapsed = time.time() - t0

            with write_lock:
                counter["n"] += 1
                i = counter["n"]
            arm_str = "/".join(seat_arms[s + 1] for s in range(4))
            head = f"[{i}/{len(todo)}] g{g} rot{rot} c{ch} ({arm_str})"

            if proc.returncode != 0 or not raw.exists():
                tail = "\n    ".join(proc.stderr.strip().splitlines()[-6:])
                print(f"{head}\n  FAILED rc={proc.returncode}\n    {tail}",
                      flush=True)
                return

            meta, games = parse_cell(raw, seat_arms)
            got = list(zip(meta.get("agents", []), meta.get("profiles", [])))
            want = [tuple(ARMS[seat_arms[s + 1]].split(":")) for s in range(4)]
            if got != want:
                print(f"{head}\n  ARM MISMATCH: asked {want}, shim ran {got}",
                      flush=True)
                return

            wins = {a: 0 for a in ARM_ORDER}
            for gm in games:
                if gm["winner_arm"]:
                    wins[gm["winner_arm"]] += 1
            censored = sum(1 for gm in games if gm["timed_out"])
            row = {
                "group": g, "rotation": rot, "chunk": ch,
                "seat_arms": {str(k): v for k, v in seat_arms.items()},
                # The extra field vs the mirror rows. analyze_h2h.py uses it to
                # verify (deck, arm) balance from the data rather than trusting
                # the square in this file.
                "seat_decks": {str(k): v for k, v in seat_decks.items()},
                "arms": ARMS, "games_requested": args.games,
                "games_per_cell": args.games_per_cell, "clock": args.clock,
                "shim_sha256_16": shim_sha, "elapsed_s": round(elapsed, 1),
                "games_played": len(games), "censored": censored,
                "wins": wins, "games": games,
            }
            with write_lock:
                with results_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
            if not args.keep_raw:
                raw.unlink(missing_ok=True)

            rate = counter["n"] * args.games_per_cell / max(
                1e-9, (time.time() - t_start) / 60)
            print(f"{head}  {len(games)}g in {elapsed / 60:.1f}m, "
                  f"censored {censored}, wins {wins}  [{rate:.2f} games/min]",
                  flush=True)
        finally:
            slots.put(worker)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        list(ex.map(run_cell, todo))

    total_min = (time.time() - t_start) / 60
    print(f"\ndone in {total_min:.1f} min "
          f"({counter['n'] * args.games_per_cell / max(1e-9, total_min):.2f} games/min)")
    print(f"results: {results_path}")


if __name__ == "__main__":
    main()
