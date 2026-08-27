#!/usr/bin/env python3
"""Sim the full 66-precon cohort the way humans actually played it.

Ground truth is playgroup.gg: 10,982 real games, 66 Commander precons, win
rates 12.0-40.9%, mean 24.2% against a 25% four-player null. That mean is the
tell -- the humans played precons AGAINST EACH OTHER in four-player pods.

The earlier correlation pilot instead sat each precon against three fixed
Commander 2014 controls, and its own notes flag that as a defect (STUDY_PLAN
section 3d, "controls too weak"). It is why every deck inflated: beating three
weak old precons is easy, so stock Forge reported 19-53% against a human range
of 12-41%, calibration slope 0.47.

This matches the generating process instead. Every game is four cohort decks,
which is also 4x cheaper: one game yields four deck-observations, not one.

Design: R rounds. Each round shuffles the cohort and cuts 16 pods of four (two
decks sit out; a different two each round, because the shuffle is seeded by
round). Each pod plays 4 invocations with the deck order rotated one seat, so
every deck sits in every seat equally often and Forge's seat bias cancels.

Resumable: a cell whose output file already exists is skipped, so partial
results can be analysed while the rest runs.

Usage:
  python3 studies/precon_predict/run_cohort.py --rounds 6 --games 2 --workers 14
"""
from __future__ import annotations

import argparse, json, os, random, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SEAT_RE = re.compile(r"^Ai\((\d+)\)-")


def forge_jar():
    hits = sorted(Path(os.path.expanduser("~/forge")).glob(
        "forge-gui-desktop-*-jar-with-dependencies.jar"))
    if not hits:
        sys.exit("Forge jar not found")
    return str(hits[-1])


def shim_jar(explicit):
    p = Path(explicit or os.path.expanduser(
        "~/simlab-forge-shim/simlab-forge-shim.jar"))
    if not p.is_file():
        sys.exit(f"shim jar missing: {p}")
    return str(p)


def pods_for_round(cohort, rnd):
    """Deterministic per round, so a resumed run rebuilds the same pods."""
    idx = list(range(len(cohort)))
    random.Random(1000 + rnd).shuffle(idx)
    usable = len(cohort) - (len(cohort) % 4)
    return [idx[i:i + 4] for i in range(0, usable, 4)]


def run_cell(spec):
    cohort, rnd, pod_i, inv, order, out, games, clock, jars, heap, agent = spec
    if not (out.exists() and out.stat().st_size > 0):
        decks = [cohort[i]["file"] for i in order]
        cmd = ["java", f"-Xmx{heap}", "-cp", f"{jars[0]}{os.pathsep}{jars[1]}",
               "simlab.shim.SimShim", "--decks", *decks,
               "--games", str(games), "--timeout", str(clock), "--out", str(out)]
        if agent:
            # ABSOLUTE: java runs with cwd=~/forge, so a relative plans path
            # silently resolves to nothing and every cell produces no games.
            cmd += ["--plans", str(Path(agent).resolve()), "--seat-pilots",
                    ",".join(["plan:SimLabHuman"] * 4)]
        subprocess.run(cmd, cwd=os.path.expanduser("~/forge"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
    return tally(cohort, order, out)


def tally(cohort, order, out):
    """Map a winner back to a deck by SEAT, never by name: names can collide
    and Ai(n)- also looks like Forge's (123) instance-id syntax."""
    rows = []
    if not out.exists():
        return rows
    for line in out.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("rec") != "result":
            continue
        seats = [cohort[i]["name"] for i in order]
        w = r.get("winner")
        seat = None
        if w and not r.get("draw"):
            m = SEAT_RE.match(w)
            if m:
                seat = int(m.group(1)) - 1
        rows.append({"seats": seats, "winner_seat": seat,
                     "draw": bool(r.get("draw")) or seat is None})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--games", type=int, default=2, help="games per invocation")
    ap.add_argument("--clock", type=int, default=1200)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--heap", default="3g")
    ap.add_argument("--shim-jar", default=None)
    ap.add_argument("--agent-plans", default=None,
                    help="plans JSON -> run all four seats as plan agents")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cohort = json.loads((HERE / "cohort.json").read_text(encoding="utf-8"))
    # RESOLVE: java runs with cwd=~/forge, so a relative --out silently
    # resolves there, the shim cannot create the file, and every cell produces
    # nothing. Same trap as --plans.
    out_dir = Path(args.out).resolve() if args.out else HERE / (
        "runs_agent" if args.agent_plans else "runs_stock")
    out_dir.mkdir(parents=True, exist_ok=True)
    jars = (shim_jar(args.shim_jar), forge_jar())

    specs = []
    for rnd in range(args.rounds):
        for pod_i, pod in enumerate(pods_for_round(cohort, rnd)):
            for inv in range(4):
                order = pod[inv:] + pod[:inv]
                specs.append((cohort, rnd, pod_i, inv, order,
                              out_dir / f"c_r{rnd}_p{pod_i:02d}_i{inv}.jsonl",
                              args.games, args.clock, jars, args.heap,
                              args.agent_plans))
    done = sum(1 for s in specs if s[5].exists() and s[5].stat().st_size > 0)
    total = len(specs) * args.games
    print(f"cohort   {len(cohort)} decks, {args.rounds} rounds x "
          f"{len(pods_for_round(cohort,0))} pods x 4 seat-rotations")
    print(f"games    {total} total, ~{args.rounds*4*args.games} per deck, "
          f"clock {args.clock}s, {args.workers} workers")
    print(f"arm      {'AGENT (all four seats)' if args.agent_plans else 'stock Forge'}")
    print(f"resume   {done}/{len(specs)} cells already done\n", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(run_cell, specs))

    wins, played = {}, {}
    for rows in results:
        for row in rows:
            for s in row["seats"]:
                played[s] = played.get(s, 0) + 1
            if not row["draw"]:
                w = row["seats"][row["winner_seat"]]
                wins[w] = wins.get(w, 0) + 1
    recs = []
    for d in cohort:
        n = played.get(d["name"], 0)
        recs.append({"name": d["name"], "human": d["human"],
                     "human_n": d["n"], "sim_games": n,
                     "sim_wins": wins.get(d["name"], 0),
                     "sim_rate": (wins.get(d["name"], 0) / n) if n else None})
    (out_dir / "cohort_results.json").write_text(
        json.dumps(recs, indent=1), encoding="utf-8")
    got = [r for r in recs if r["sim_games"]]
    if not got:
        print("NO GAMES PRODUCED -- every cell failed. Check that "
              "--out and --agent-plans are absolute: java runs "
              "with cwd=~/forge.")
        return 1
    print(f"\ndecks with data: {len(got)}/{len(recs)}; "
          f"median games/deck: {sorted(r['sim_games'] for r in got)[len(got)//2]}")
    print(f"wrote {out_dir/'cohort_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
