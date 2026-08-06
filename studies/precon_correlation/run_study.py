#!/usr/bin/env python3
"""Run the precon correlation study's sim arms.

For each test precon, plays a 4-player seat-rotated pod against the three fixed
C14 control decks, under each requested arm, and records the outcome.

Win rates are computed here from the shim's own `rec:"result"` records rather
than from `run_sim.py`'s summary, because the summary counts clock-timeout games
as legitimate wins (STUDY_PLAN.md §3a). Timeout games are reported and excluded.

Resumable: completed (deck, arm, games, clock) cells are skipped, so the run can
be interrupted and restarted.

Usage:
    # feasibility pilot, 8 decks x 2 arms
    python3 studies/precon_correlation/run_study.py --pilot --games 32 --clock 900

    # full run over a cohort
    python3 studies/precon_correlation/run_study.py --cohort all --games 64 --clock 900
    python3 studies/precon_correlation/run_study.py --cohort pre2025 --games 64 --clock 900

    python3 studies/precon_correlation/run_study.py --pilot --dry-run
"""

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ENGINE = REPO / "engine"
FORGE_PRECONS = Path(os.path.expanduser("~/forge/res/quest/commanderprecons"))

CONTROLS = [
    "Built from Scratch [C14] [2014].dck",   # R, artifacts
    "Guided by Nature [C14] [2014].dck",     # G, elves
    "Sworn to Darkness [C14] [2014].dck",    # B, demons
]

# Feasibility pilot: the ground-truth extremes plus two 2026 sets to test
# Forge card-script coverage, plus one mid-table deck. STUDY_PLAN.md §6.
PILOT = [
    "Planeswalker Party",      # 40.87% - top of ground truth
    "Tricky Terrain",          # 32.07%
    "Explorers of the Deep",   # 25.25% - mid
    "Doom Prevails",           # 21.06% - 2026 set, coverage test
    "Blight Curse",            # 18.49% - 2026 set, coverage test
    "Mutant Menace",           # 15.12%
    "Grand Larceny",           # 13.20%
    "Deadly Disguise",         # 11.96% - bottom of ground truth
]

ARMS = {
    # arm name -> extra run_sim.py flags. Both use the shim, so the harness is
    # held constant and only the decision policy varies.
    "shim_stock": ["--agent", "shim"],
    "agent_v3": ["--humanize"],
}

SEAT_RE = re.compile(r"^Ai\(\d+\)-")


def strip_seat(name: str) -> str:
    """'Ai(2)-Grand Larceny [OTC] [2024]' -> 'Grand Larceny [OTC] [2024]'.

    Note the deliberate anchor: Forge also writes '(123)' instance ids, so an
    unanchored strip would corrupt card/deck names (CLAUDE.md gotcha 5).
    """
    return SEAT_RE.sub("", name).strip()


def deck_label(forge_file: str) -> str:
    """The [metadata] Name Forge reports, which is the .dck stem."""
    return forge_file[:-4] if forge_file.endswith(".dck") else forge_file


def parse_results(jsonl_paths):
    """Collect every rec:"result" record across a run's rotation files."""
    games = []
    for p in jsonl_paths:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"rec":"result"' not in line.replace(" ", ""):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("rec") != "result":
                continue
            games.append({
                "winner": strip_seat(d["winner"]) if d.get("winner") else None,
                "draw": bool(d.get("draw")),
                "timed_out": bool(d.get("timedOut")),
                "turns": d.get("turns"),
                "ms": d.get("ms"),
            })
    return games


def summarize(games, test_label):
    """Win rate for the test deck, computed two ways for transparency."""
    n = len(games)
    timed_out = sum(1 for g in games if g["timed_out"])
    draws = sum(1 for g in games if g["draw"])
    clean = [g for g in games if not g["timed_out"] and not g["draw"]]
    clean_wins = sum(1 for g in clean if g["winner"] == test_label)
    # The naive figure the product would report today, kept for comparison.
    naive_wins = sum(1 for g in games if g["winner"] == test_label)
    return {
        "games_played": n,
        "timed_out": timed_out,
        "draws": draws,
        "games_clean": len(clean),
        "wins_clean": clean_wins,
        "win_rate_clean": (clean_wins / len(clean)) if clean else None,
        "wins_naive": naive_wins,
        "win_rate_naive": (naive_wins / n) if n else None,
        "mean_turns": (sum(g["turns"] for g in games if g["turns"]) /
                       max(1, sum(1 for g in games if g["turns"]))),
        "mean_ms": (sum(g["ms"] for g in games if g["ms"]) /
                    max(1, sum(1 for g in games if g["ms"]))),
    }


def load_cohort(which):
    manifest = json.loads((HERE / "manifest.json").read_text())
    precons = manifest["precons"]
    if which == "pilot":
        want = set(PILOT)
        rows = [p for p in precons if p["name"] in want]
        missing = want - {p["name"] for p in rows}
        if missing:
            sys.exit(f"pilot decks not in manifest: {sorted(missing)}")
        return rows
    if which == "all":
        return precons
    if which == "pre2025":
        # Reuse design.py's set->year table so the definition lives in one place.
        sys.path.insert(0, str(HERE))
        from design import SET_YEAR
        return [p for p in precons if SET_YEAR.get(p["set"], 9999) <= 2024]
    sys.exit(f"unknown cohort {which!r}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true", help="run the 8-deck feasibility pilot")
    g.add_argument("--cohort", choices=["all", "pre2025"], help="run a full cohort")
    ap.add_argument("--games", type=int, default=32, help="games per deck per arm (split across 4 rotations)")
    ap.add_argument("--clock", type=int, default=900, help="per-game timeout seconds")
    ap.add_argument("--heap", default="3g",
                    help="JVM heap per worker; heap x workers must fit in RAM")
    ap.add_argument("--workers", type=int, default=1,
                    help="concurrent sims. Each gets its own FORGE_USER_DIR so "
                         "deck staging cannot race (STUDY_PLAN.md 3b). Defaults "
                         "to 1 because --clock is WALL clock: see "
                         "--i-accept-clock-contamination")
    ap.add_argument("--i-accept-clock-contamination", action="store_true",
                    help="required to run --workers > 1. --clock is wall-clock, "
                         "so contending workers slow every game and decide which "
                         "ones get force-drawn. Censoring is already the pilot's "
                         "dominant confound (7.8%% stock vs 19.9%% agent), and it "
                         "is not comparable across cells run at different "
                         "concurrency. Use only for throughput work whose win "
                         "rates you will not compare.")
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    ap.add_argument("--out", default=None, help="output dir (default studies/.../runs)")
    ap.add_argument("--shim-jar", default=None,
                    help="shim jar to pin for the whole study. Default: copy the "
                         "current jar into pinned/ and use that, so another "
                         "session rebuilding the shared jar cannot change the "
                         "arms mid-run (CLAUDE.md: concurrent sessions edit this tree)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cohort = load_cohort("pilot" if args.pilot else args.cohort)
    out_dir = Path(args.out) if args.out else HERE / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.jsonl"

    done = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            done.add((r["precon"], r["arm"], r["games_requested"], r["clock"]))

    forge_jar = os.environ.get("FORGE_JAR") or str(
        Path(os.path.expanduser("~/forge")) / "forge-gui-desktop-2.0.13-jar-with-dependencies.jar")

    # Pin the shim. The shared jar was rebuilt mid-session once already
    # (2026-08-03 14:49, shim commit 77e4ddb), which would silently make the two
    # arms non-comparable. Copy once, hash it, and record the hash on every row.
    import hashlib
    import shutil
    if args.shim_jar:
        pinned = Path(args.shim_jar)
    else:
        src = Path(os.path.expanduser(
            "~/Desktop/Personal/simlab-forge-shim/simlab-forge-shim.jar"))
        pinned = HERE / "pinned" / "simlab-forge-shim.jar"
        pinned.parent.mkdir(parents=True, exist_ok=True)
        if not pinned.exists():
            if not src.is_file():
                sys.exit(f"shim jar not found at {src}; pass --shim-jar")
            shutil.copy2(src, pinned)
            print(f"pinned shim jar <- {src}")
    if not pinned.is_file():
        sys.exit(f"pinned shim jar missing: {pinned}")
    shim_sha = hashlib.sha256(pinned.read_bytes()).hexdigest()[:16]
    print(f"shim      {pinned} (sha256 {shim_sha})")

    cells = [(p, arm) for p in cohort for arm in args.arms]
    todo = [(p, a) for p, a in cells
            if (p["name"], a, args.games, args.clock) not in done]
    workers = max(1, args.workers)
    if workers > 1 and not args.i_accept_clock_contamination:
        sys.exit(
            f"--workers {workers} refused. --clock is wall-clock, so N workers "
            f"contending for CPU lengthen every game and change WHICH games hit "
            f"the clock. Timeout censoring is the pilot's dominant confound, and "
            f"cells run at different concurrency are not comparable to each "
            f"other. Run serial (the default), or pass "
            f"--i-accept-clock-contamination if these win rates will not be "
            f"compared. Every row records the concurrency it ran at either way.")
    est_h = len(todo) * args.games * 95 / 3600.0
    print(f"cohort {len(cohort)} decks x {len(args.arms)} arms = {len(cells)} cells")
    print(f"already done {len(cells) - len(todo)}, to run {len(todo)}")
    print(f"{args.games} games/cell, clock {args.clock}s, "
          f"{workers} workers x {args.heap} heap")
    print(f"rough estimate {est_h:.1f} h serial / {est_h / workers:.1f} h at "
          f"{workers} workers, at 95 s/game")
    if args.dry_run:
        for p, a in todo:
            print(f"  {a:<11} {p['human_win_rate']:>6.2f}%  {p['forge_file']}")
        return

    # Each worker gets a private Forge profile so concurrent stage_decks() calls
    # cannot race on one shared deck dir.
    slots = queue.Queue()
    for w in range(workers):
        prof = out_dir / "forge_profiles" / f"w{w}"
        (prof / "decks" / "commander").mkdir(parents=True, exist_ok=True)
        slots.put(prof)

    write_lock = threading.Lock()
    counter = {"n": 0}

    def run_cell(cell):
        p, arm = cell
        prof = slots.get()
        try:
            label = deck_label(p["forge_file"])
            slug = re.sub(r"[^a-z0-9]+", "-", p["name"].lower()).strip("-")
            run_id = f"study_{slug}_{arm}_g{args.games}_c{args.clock}"
            cmd = [sys.executable, "run_sim.py",
                   "--decks", p["forge_file"], *CONTROLS,
                   "--deck-dir", str(FORGE_PRECONS),
                   "--games", str(args.games), "--rotate",
                   "--format", "Commander", "--quiet",
                   "--clock", str(args.clock), "--heap", args.heap,
                   "--out", str(out_dir), "--run-id", run_id,
                   *ARMS[arm]]
            t0 = time.time()
            proc = subprocess.run(
                cmd, cwd=str(ENGINE),
                env={**os.environ, "FORGE_JAR": forge_jar,
                     "FORGE_USER_DIR": str(prof),
                     "SIMLAB_SHIM_JAR": str(pinned)},
                capture_output=True, text=True)
            elapsed = time.time() - t0

            with write_lock:
                counter["n"] += 1
                i = counter["n"]
            head = f"[{i}/{len(todo)}] {arm} | {p['name']} (human {p['human_win_rate']:.2f}%)"

            if proc.returncode != 0:
                tail = "\n    ".join(proc.stderr.strip().splitlines()[-6:])
                print(f"{head}\n  FAILED rc={proc.returncode}\n    {tail}", flush=True)
                return

            jsonls = sorted(out_dir.glob(f"shim_raw_{run_id}_rot*.jsonl"))
            games = parse_results(jsonls)
            summ = summarize(games, label)
            # Card-script problems surface as stderr noise; keep a sample.
            errs = [l for l in proc.stderr.splitlines()
                    if re.search(r"error|exception|unsupported|not implemented",
                                 l, re.I) and not l.startswith("shim:")]
            row = {
                "precon": p["name"], "forge_file": p["forge_file"],
                "deck_label": label, "arm": arm,
                "human_win_rate": p["human_win_rate"], "human_games": p["human_games"],
                "tier": p["tier"], "set": p["set"],
                "games_requested": args.games, "clock": args.clock,
                # The clock is wall-clock, so concurrency is part of the
                # experimental condition, not a scheduling detail. Recorded on
                # every row so a later analysis can segment or exclude cells
                # rather than silently pooling them.
                "workers": workers,
                "shim_sha256_16": shim_sha,
                "controls": CONTROLS, "elapsed_s": round(elapsed, 1),
                **summ,
                "stderr_flags": errs[:5], "stderr_flag_count": len(errs),
            }
            with write_lock:
                with results_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
            wr = summ["win_rate_clean"]
            wr_s = f"{wr:.1%}" if wr is not None else "n/a"
            print(f"{head}\n  clean {summ['games_clean']}/{summ['games_played']}, "
                  f"timeouts {summ['timed_out']}, draws {summ['draws']}, "
                  f"win rate {wr_s} | mean {summ['mean_turns']:.0f} turns, "
                  f"{summ['mean_ms'] / 1000:.0f} s/game, cell {elapsed / 60:.1f} min"
                  + (f", {len(errs)} stderr flags" if errs else ""), flush=True)
        finally:
            slots.put(prof)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(run_cell, todo))

    print(f"\nresults -> {results_path}")


if __name__ == "__main__":
    main()
