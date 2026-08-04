#!/usr/bin/env python3
"""Re-run the agent v1/v2/v3 comparison pods at clock 900 with the fixed shim.

`engine/SIM_CALIBRATION.md`'s agent win-rate lines were all measured at the old
`--clock 120` default, before shim commit 77e4ddb forced a draw on timeout. At
that clock a large share of games were decided by the clock and credited to a
quasi-arbitrary winner, which pulls every deck toward the 1/N baseline. That is
an alternative explanation for the doc's "the agent compressed the win-rate
spread" claim, and this script produces the data to test it.

Design notes:

- **Control arm is `--agent shim`, not `--agent forge`.** Both arms then share
  the shim harness and differ only in decision policy. `--agent forge` would
  change the pilot *and* the harness (stdout scraping vs typed GameLog) at once
  (STUDY_PLAN.md §3).
- **The shim jar is pinned.** Another session rebuilding the shared jar would
  otherwise change the arms mid-run (STUDY_PLAN.md §3c). Every cell records the
  jar's sha256 prefix.
- **Arms are interleaved, not run back to back.** The clock is a *wall-clock*
  timeout, so a busy machine manufactures timeouts. Interleaving makes whatever
  contention exists apply to both arms roughly equally.
- **Keep `--workers` low.** Measured: the same decks at the same 600 s clock
  timed out 0/27 at 4 workers and 8/17 at 10 workers on this 12-core box.

Usage:
    python3 run_pods.py --games 64 --workers 4
    python3 run_pods.py --dry-run
    python3 run_pods.py --wait-for-idle        # queue behind a running study
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ENGINE = REPO / "engine"
DECKS = ENGINE / "decks"

# The three pods whose win-rate lines are quoted in SIM_CALIBRATION.md.
# 'kilo' in the v1/v2 section is taken as kilo_helm_final, the build the later
# sections name explicitly.
PODS = {
    "v1v2": [
        "kilo_helm_final.dck",
        "drana_vampires.dck",
        "wilhelt_zombies.dck",
        "wyleth_voltron.dck",
    ],
    "v3_combo": [
        "atraxa_counters.dck",
        "urdragon_dragons.dck",
        "meren_graveyard.dck",
        "kilo_helm_final.dck",
    ],
    "v3_tutor": [
        "krenko_goblins.dck",
        "atraxa_counters.dck",
        "kilo_helm_final.dck",
        "drana_vampires.dck",
    ],
}

ARMS = {
    "shim_stock": ["--agent", "shim"],
    "agent_v3": ["--humanize"],
}

PRINT_LOCK = threading.Lock()


def say(msg):
    with PRINT_LOCK:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sha16(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def find_shim():
    for cand in [
        os.environ.get("SIMLAB_SHIM_JAR"),
        os.path.expanduser("~/Desktop/Personal/simlab-forge-shim/simlab-forge-shim.jar"),
    ]:
        if cand and Path(cand).exists():
            return Path(cand)
    sys.exit("no shim jar found; set SIMLAB_SHIM_JAR")


def forge_busy():
    """True while any Forge sim (ours or another session's) is running."""
    try:
        out = subprocess.run(["ps", "-axo", "command"], capture_output=True,
                             text=True, timeout=30).stdout
    except Exception:
        return False
    return ("simlab.shim.SimShim" in out) or ("run_sim.py" in out)


def wait_for_idle(poll=120, settle=3):
    """Block until the box has been free of Forge sims for `settle` polls."""
    quiet = 0
    while quiet < settle:
        if forge_busy():
            if quiet:
                say("another sim reappeared; resetting the idle timer")
            quiet = 0
        else:
            quiet += 1
            say(f"box idle ({quiet}/{settle})")
        if quiet < settle:
            time.sleep(poll)
    say("box idle, starting")


def cell_done(out_dir, run_id, games):
    """Resumability: count result records already written for this cell."""
    n = 0
    for f in out_dir.glob(f"shim_raw_{run_id}_rot*.jsonl"):
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            n += sum(1 for line in fh if '"rec":"result"' in line)
    return n


def run_cell(pod, arm, args, shim, out_dir, worker):
    run_id = f"spread_{pod}_{arm}_g{args.games}_c{args.clock}"
    have = cell_done(out_dir, run_id, args.games)
    if have >= args.games:
        say(f"skip {run_id} (already has {have} games)")
        return {"pod": pod, "arm": arm, "run_id": run_id, "skipped": True}

    prof = out_dir / "forge_profiles" / f"w{worker}"
    prof.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-u", "run_sim.py",
        "--decks", *PODS[pod],
        "--deck-dir", str(DECKS),
        "--games", str(args.games),
        "--rotate",
        "--format", "Commander",
        "--quiet",
        "--clock", str(args.clock),
        "--heap", args.heap,
        "--out", str(out_dir),
        "--run-id", run_id,
        *ARMS[arm],
    ]

    env = dict(os.environ)
    env["FORGE_USER_DIR"] = str(prof)
    env["SIMLAB_SHIM_JAR"] = str(shim)

    if args.dry_run:
        say("DRY " + " ".join(cmd))
        return {"pod": pod, "arm": arm, "run_id": run_id, "dry_run": True}

    say(f"start {run_id} (worker {worker})")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ENGINE), env=env,
                          capture_output=True, text=True)
    dt = time.time() - t0
    played = cell_done(out_dir, run_id, args.games)
    say(f"done  {run_id}  {played} games in {dt/60:.1f} min  rc={proc.returncode}")
    if proc.returncode != 0:
        say(f"  stderr tail: {proc.stderr.strip()[-400:]}")

    return {
        "pod": pod, "arm": arm, "run_id": run_id,
        "games_requested": args.games, "games_played": played,
        "clock": args.clock, "elapsed_s": round(dt, 1),
        "shim_sha256_16": sha16(shim),
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr.strip()[-2000:] if proc.returncode else "",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--games", type=int, default=64)
    ap.add_argument("--clock", type=int, default=900)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--heap", default="3g")
    ap.add_argument("--out", default=str(HERE / "runs"))
    ap.add_argument("--pods", nargs="*", default=list(PODS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wait-for-idle", action="store_true",
                    help="block until no other Forge sim is running")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [d for pod in args.pods for d in PODS[pod] if not (DECKS / d).exists()]
    if missing:
        sys.exit(f"missing deck files: {sorted(set(missing))}")

    src = find_shim()
    pinned = out_dir / "pinned"
    pinned.mkdir(exist_ok=True)
    jar = pinned / "simlab-forge-shim.jar"
    if not jar.exists():
        jar.write_bytes(src.read_bytes())
        say(f"pinned shim {src} -> {jar} (sha16 {sha16(jar)})")
    else:
        say(f"using pinned shim {jar} (sha16 {sha16(jar)})")

    if args.wait_for_idle and not args.dry_run:
        wait_for_idle()

    # Interleave arms so contention, if any, hits both roughly equally.
    cells = []
    for pod in args.pods:
        for arm in ARMS:
            cells.append((pod, arm))
    cells.sort(key=lambda c: (list(ARMS).index(c[1]), c[0]))
    ordered = []
    half = len(cells) // 2
    for i in range(half):
        ordered.append(cells[i])
        ordered.append(cells[i + half])

    say(f"{len(ordered)} cells, {args.games} games each, clock {args.clock}, "
        f"{args.workers} workers")

    slots = list(range(args.workers))
    slot_lock = threading.Lock()

    def work(cell):
        with slot_lock:
            w = slots.pop()
        try:
            return run_cell(cell[0], cell[1], args, jar, out_dir, w)
        finally:
            with slot_lock:
                slots.append(w)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(work, ordered))
    say(f"all cells finished in {(time.time()-t0)/60:.1f} min")

    if not args.dry_run:
        res_path = out_dir / "cells.jsonl"
        with open(res_path, "a", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r) + "\n")
        say(f"wrote {res_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
