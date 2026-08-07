#!/usr/bin/env python3
"""Run the engine-strength head-to-head: the full 2x2 in one mirror pod.

Four seats all play the SAME decklist, one seat per arm, so deck strength
cancels exactly and any deviation from the 25% null is piloting. See PLAN.md.

    A  plan  + SimLabHuman   what ships today
    B  stock + Default       stock Forge
    C  stock + SimLabHuman   floodgate without the gate
    D  plan  + Default       our policy without the floodgate

Why this does not go through run_sim.py: its --rotate rotates DECK order, which
is a no-op when every deck is identical. What has to move across seats here is
the ARM assignment, because Forge's seat bias is measured at seat 1 ~11% vs
seat 4 ~36% (run_sim.py:308) and would otherwise swamp any skill effect. So this
drives the shim directly and rotates --seat-pilots instead.

Win rates come from the shim's own rec:"result" records. Timed-out games have no
winner and are excluded from win share, but their per-seat survival IS recorded,
because censored games are the long ones and dropping them silently drops a
biased slice (PLAN.md section 4).

Resumable: completed (deck, rotation, chunk) cells are skipped.

Usage:
    python3 studies/skill_headtohead/run_h2h.py --games 96 --workers 14
    python3 studies/skill_headtohead/run_h2h.py --dry-run
"""

import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ENGINE = REPO / "engine"
CORRELATION = REPO / "studies" / "precon_correlation"

# Arm identity is the PAIR (controller, profile). SimLabHuman is Default with
# the counterspell chances maxed, designed to be gated by the plan controller's
# threat veto, so "plan" alone does not say what a seat was running.
ARMS = {
    "A": "plan:SimLabHuman",
    "B": "stock:Default",
    "C": "stock:SimLabHuman",
    "D": "plan:Default",
}
ARM_ORDER = ["A", "B", "C", "D"]

# Same 8 precons as the correlation pilot. In a mirror the deck does not set
# difficulty, so these are here for ARCHETYPE COVERAGE: to test whether any
# strength edge is archetype-uniform, which is what a correction layer needs.
COHORT = [
    "Planeswalker Party",
    "Tricky Terrain",
    "Explorers of the Deep",
    "Doom Prevails",
    "Blight Curse",
    "Mutant Menace",
    "Grand Larceny",
    "Deadly Disguise",
]

SEAT_RE = re.compile(r"^Ai\((\d+)\)-")


def seat_of(player_name):
    """'Ai(3)-Deck Name' -> 3. Note Ai(n)- also looks like Forge's (123)
    instance-id syntax, so this stays anchored (CLAUDE.md gotcha 5)."""
    m = SEAT_RE.match(player_name or "")
    return int(m.group(1)) if m else None


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def forge_precons_dir():
    """Forge's bundled Commander precons. Not vendored: resolved at run time
    where Forge is installed (CLAUDE.md forbids vendoring Forge)."""
    env = os.environ.get("FORGE_PRECONS")
    if env:
        return Path(env)
    return Path(os.path.expanduser("~")) / "forge" / "res" / "quest" / "commanderprecons"


def find_forge_jar():
    env = os.environ.get("FORGE_JAR")
    if env:
        return Path(env)
    home = Path(os.path.expanduser("~")) / "forge"
    hits = sorted(home.glob("forge-gui-desktop-*-jar-with-dependencies.jar"))
    if not hits:
        sys.exit(f"Forge jar not found under {home}; set FORGE_JAR")
    return hits[-1]


def load_cohort():
    """Join the cohort names to Forge .dck files via the correlation study's
    manifest, so the name->file mapping lives in exactly one place."""
    manifest = json.loads((CORRELATION / "manifest.json").read_text(encoding="utf-8"))
    by_name = {p["name"]: p for p in manifest["precons"]}
    rows, missing = [], []
    for name in COHORT:
        if name not in by_name:
            missing.append(name)
        else:
            rows.append(by_name[name])
    if missing:
        sys.exit(f"not in manifest: {missing}")
    return rows


def build_plans_for(deck_path, out_path):
    """Deck plans are OUR strategy data; they cross to the GPL shim as JSON."""
    sys.path.insert(0, str(ENGINE))
    from deck_plan import build_plans
    plans = build_plans([deck_path])
    out_path.write_text(json.dumps(plans, indent=2), encoding="utf-8")
    return list(plans["decks"].keys())


def parse_cell(jsonl_path, seat_arms):
    """Per-game outcomes with each seat's arm attached.

    seat_arms maps 1-based seat number -> arm letter. Survival entries carry
    their own seat name rather than trusting positional alignment, because
    getRegisteredPlayers() order is Forge's to decide.
    """
    meta, games = None, []
    for line in jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"rec"' not in line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("rec") == "meta":
            meta = d
        elif d.get("rec") == "result":
            win_seat = seat_of(d.get("winner"))
            seats = {}
            for s in d.get("seats", []):
                sn = seat_of(s.get("name"))
                if sn is not None:
                    seats[seat_arms[sn]] = {"life": s.get("life"),
                                            "alive": bool(s.get("alive"))}
            games.append({
                "timed_out": bool(d.get("timedOut")),
                "draw": bool(d.get("draw")),
                "turns": d.get("turns"),
                "ms": d.get("ms"),
                # None for a censored or drawn game. Never inferred from
                # survival: surviving is not winning (PLAN.md section 4).
                "winner_arm": seat_arms.get(win_seat) if win_seat else None,
                "seats": seats,
            })
    return meta, games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=96,
                    help="games per deck, split across 4 arm rotations")
    ap.add_argument("--games-per-cell", type=int, default=8,
                    help="games per shim invocation. Small cells keep results "
                         "durable: the correlation pilot lost hours to 32-game "
                         "cells where nothing landed until the cell finished")
    ap.add_argument("--clock", type=int, default=1260,
                    help="per-game timeout seconds (PLAN.md section 4)")
    ap.add_argument("--heap", default="3g")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--decks", nargs="+", default=None,
                    help="subset of the cohort by name (default: all 8)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--shim-jar", default=None)
    ap.add_argument("--keep-raw", action="store_true",
                    help="keep the full shim JSONL per cell (~4 MB per 8 games). "
                         "Off by default: every field the pre-registered "
                         "analysis needs is copied into results.jsonl first")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.games % (4 * args.games_per_cell):
        sys.exit(f"--games {args.games} must be divisible by 4 rotations x "
                 f"{args.games_per_cell} games/cell. Four rotations are "
                 f"mandatory: they put each arm in each seat exactly once, "
                 f"which is what cancels Forge's seat bias.")
    chunks = args.games // 4 // args.games_per_cell

    cohort = load_cohort()
    if args.decks:
        want = set(args.decks)
        cohort = [p for p in cohort if p["name"] in want]
        if not cohort:
            sys.exit(f"no cohort deck matched {sorted(want)}")

    out_dir = Path(args.out) if args.out else HERE / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    done = set()
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["precon"], r["rotation"], r["chunk"],
                          r["games_requested"], r["clock"]))

    forge_jar = find_forge_jar()
    precons = forge_precons_dir()
    if not precons.is_dir():
        sys.exit(f"Forge precons not found: {precons}. Set FORGE_PRECONS.")

    # Pin the shim. A shared jar rebuilt mid-study silently changes the arms
    # underneath it; that happened once already during the correlation pilot
    # (STUDY_PLAN.md 3c). Hash it and record the hash on every row.
    pinned = Path(args.shim_jar) if args.shim_jar else HERE / "pinned" / "simlab-forge-shim.jar"
    if not pinned.is_file():
        sys.exit(f"pinned shim jar missing: {pinned}")
    shim_sha = hashlib.sha256(pinned.read_bytes()).hexdigest()[:16]

    cells = []
    for p in cohort:
        for rot in range(4):
            for ch in range(chunks):
                cells.append((p, rot, ch))
    todo = [c for c in cells
            if (c[0]["name"], c[1], c[2], args.games, args.clock) not in done]

    print(f"shim      {pinned} (sha256 {shim_sha})")
    print(f"forge     {forge_jar}")
    print(f"cohort    {len(cohort)} decks x 4 rotations x {chunks} chunks "
          f"= {len(cells)} cells of {args.games_per_cell} games")
    print(f"          {len(cohort) * args.games} games total, clock {args.clock}s")
    print(f"already done {len(cells) - len(todo)}, to run {len(todo)}")
    # 363 s/game measured on 8 all-stock mirror games at clock 1260 (PLAN.md 4).
    # All-stock is the FASTEST arm mix; plan agents lengthen games, so this is a
    # floor and the real number is what the run reports.
    est_h = len(todo) * args.games_per_cell * 363 / 3600.0
    print(f"estimate  {est_h:.1f} h serial / {est_h / max(1, args.workers):.1f} h "
          f"at {args.workers} workers, at a measured-floor 363 s/game")
    if args.dry_run:
        for p, rot, ch in todo[:12]:
            order = ARM_ORDER[rot:] + ARM_ORDER[:rot]
            print(f"  {p['name']:<24} rot{rot} chunk{ch}  seats={'/'.join(order)}")
        if len(todo) > 12:
            print(f"  ... and {len(todo) - 12} more")
        return

    # One plans file per deck, built up front and single-threaded so concurrent
    # cells cannot race on it. All four mirror copies share a [metadata] Name,
    # so one plan entry serves every plan seat.
    plans_dir = out_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plans_for = {}
    for p in cohort:
        pf = plans_dir / f"plans_{slugify(p['name'])}.json"
        if not pf.exists():
            src = precons / p["forge_file"]
            if not src.is_file():
                sys.exit(f"deck not found: {src}")
            keys = build_plans_for(src, pf)
            print(f"plans     {p['name']} -> {keys}")
        plans_for[p["name"]] = pf

    slots = queue.Queue()
    for w in range(max(1, args.workers)):
        d = out_dir / "workers" / f"w{w}"
        (d / "decks" / "commander").mkdir(parents=True, exist_ok=True)
        slots.put(d)

    write_lock = threading.Lock()
    counter = {"n": 0}
    t_start = time.time()

    def run_cell(cell):
        p, rot, ch = cell
        worker = slots.get()
        try:
            slug = slugify(p["name"])
            # Rotate the ARM assignment, not the deck order: the decks are
            # identical, so rotating them would do nothing.
            order = ARM_ORDER[rot:] + ARM_ORDER[:rot]
            seat_arms = {i + 1: arm for i, arm in enumerate(order)}
            spec = ",".join(ARMS[a] for a in order)

            # Four copies of one decklist. Identical [metadata] Name on purpose:
            # --seat-pilots assigns pilots positionally, so the shim no longer
            # needs distinct names to tell the seats apart.
            src = precons / p["forge_file"]
            staged = []
            for s in range(4):
                dst = worker / f"{slug}_s{s + 1}.dck"
                shutil.copy2(src, dst)
                staged.append(str(dst))

            run_id = f"h2h_{slug}_rot{rot}_c{ch}_g{args.games_per_cell}_t{args.clock}"
            raw = out_dir / f"shim_raw_{run_id}.jsonl"
            cmd = ["java", f"-Xmx{args.heap}",
                   "-cp", f"{pinned}{os.pathsep}{forge_jar}",
                   "simlab.shim.SimShim",
                   "--decks", *staged,
                   "--plans", str(plans_for[p["name"]]),
                   "--seat-pilots", spec,
                   "--games", str(args.games_per_cell),
                   "--timeout", str(args.clock),
                   "--out", str(raw)]
            t0 = time.time()
            # Forge must run from its install dir so it finds res/.
            proc = subprocess.run(
                cmd, cwd=str(forge_jar.parent),
                env={**os.environ, "FORGE_USER_DIR": str(worker)},
                capture_output=True, text=True)
            elapsed = time.time() - t0

            with write_lock:
                counter["n"] += 1
                i = counter["n"]
            head = f"[{i}/{len(todo)}] {p['name']} rot{rot} c{ch} ({'/'.join(order)})"

            if proc.returncode != 0 or not raw.exists():
                tail = "\n    ".join(proc.stderr.strip().splitlines()[-6:])
                print(f"{head}\n  FAILED rc={proc.returncode}\n    {tail}",
                      flush=True)
                return

            meta, games = parse_cell(raw, seat_arms)
            # The shim reports what each seat ACTUALLY ran. Verify it against
            # what we asked for rather than trusting the flag we passed: a run
            # mislabeled at the seat level is the failure that corrupted four
            # cells of the correlation pilot.
            got = list(zip(meta.get("agents", []), meta.get("profiles", [])))
            want = [tuple(ARMS[a].split(":")) for a in order]
            if got != want:
                print(f"{head}\n  ARM MISMATCH: asked {want}, shim ran {got}",
                      flush=True)
                return

            wins = {a: 0 for a in ARM_ORDER}
            for g in games:
                if g["winner_arm"]:
                    wins[g["winner_arm"]] += 1
            censored = sum(1 for g in games if g["timed_out"])
            row = {
                "precon": p["name"], "forge_file": p["forge_file"],
                "rotation": rot, "chunk": ch,
                "seat_arms": {str(k): v for k, v in seat_arms.items()},
                "arms": ARMS, "games_requested": args.games,
                "games_per_cell": args.games_per_cell, "clock": args.clock,
                "shim_sha256_16": shim_sha, "elapsed_s": round(elapsed, 1),
                "games_played": len(games), "censored": censored,
                "wins": wins,
                # Per-game detail so the analysis never needs the raw JSONL.
                "games": games,
            }
            with write_lock:
                with results_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
            if not args.keep_raw:
                raw.unlink(missing_ok=True)

            rate = counter["n"] * args.games_per_cell / max(1e-9, (time.time() - t_start) / 60)
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
