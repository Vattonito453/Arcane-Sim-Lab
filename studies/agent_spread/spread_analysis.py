#!/usr/bin/env python3
"""Win-rate spread analysis for stock-vs-agent sim arms.

Answers one question: does the humanized agent compress the win-rate spread
within a pod, relative to stock Forge AI playing the same pod?

`engine/SIM_CALIBRATION.md` claimed it does, on 8-game samples taken before the
timeout bug was fixed (shim 77e4ddb). Two things make that claim untestable as
originally measured:

1. Clock-forced games were credited to a quasi-arbitrary winner, which pulls
   every deck toward the 1/N baseline and manufactures compression.
2. n=8 per arm. The sampling SD of a single deck's win rate at n=8 and p=0.25 is
   15.3 pp, which is larger than the entire effect being claimed.

This tool handles (1) by excluding `timedOut` games, and quantifies (2) by
calibrating the observed spread against the spread you would see from four
*identical* decks at the same sample size (`--null-trials`).

Reads the shim's raw JSONL directly (`rec:"result"` records), not the adapter's
summary, for the same reason `run_study.py` does: the summary counts timeouts as
wins.

Usage:
    python3 spread_analysis.py <raw.jsonl | dir | glob> [...] [--json out.json]
    python3 spread_analysis.py runs/ --group-by pod-arm
    python3 spread_analysis.py --null-only --decks 4 --games 8
"""

import argparse
import glob
import json
import math
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SEAT_RE = re.compile(r"^Ai\(\d+\)-")

# Anchored, because Forge also writes '(123)' instance ids inside card and deck
# names; an unanchored strip would corrupt them (CLAUDE.md gotcha 5).
def strip_seat(name):
    return SEAT_RE.sub("", name or "").strip()


def load_raw(path):
    """Parse one shim raw JSONL into (meta, [result records])."""
    meta, results = None, []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            # Cheap prefilter: these files are ~1 MB of mostly 'entry' records.
            if '"rec":"entry"' in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # a run still in progress can end mid-line
            kind = rec.get("rec")
            if kind == "meta" and meta is None:
                meta = rec
            elif kind == "result":
                results.append(rec)
    return meta, results


def pod_key(meta):
    """Deck set, order-independent, so rotations of one pod group together."""
    players = [strip_seat(p) for p in (meta.get("players") or [])]
    return tuple(sorted(players))


def arm_of(meta, path):
    if meta.get("humanized"):
        return "agent"
    return "stock"


def wilson(k, n, z=1.96):
    """Wilson score interval. Behaves at k=0 and k=n, unlike the normal one."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def spread_sd(rates):
    """Population SD of deck win rates. The headline 'spread' number."""
    if len(rates) < 2:
        return 0.0
    return statistics.pstdev(rates)


def null_spread(n_decks, n_games, trials=20000, rng=None):
    """Spread SD you'd see from n_decks *identical* decks over n_games.

    This is the calibration the original n=8 claim lacked. Every game is awarded
    to a uniformly random seat, so any spread is pure sampling noise.
    """
    rng = rng or random.Random(20260803)
    if n_games <= 0:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0}
    sds = []
    for _ in range(trials):
        counts = [0] * n_decks
        for _ in range(n_games):
            counts[rng.randrange(n_decks)] += 1
        sds.append(spread_sd([c / n_games for c in counts]))
    sds.sort()
    return {
        "mean": statistics.fmean(sds),
        "p50": sds[len(sds) // 2],
        "p95": sds[int(0.95 * (len(sds) - 1))],
    }


def bootstrap_delta(games_a, games_b, decks, trials=10000, rng=None):
    """95% CI on (spread_a - spread_b), resampling clean games within each arm.

    games_* are lists of winner labels from timeout-excluded games.
    """
    rng = rng or random.Random(20260803)
    if not games_a or not games_b:
        return None

    def sd_of(sample):
        counts = {d: 0 for d in decks}
        for w in sample:
            if w in counts:
                counts[w] += 1
        n = len(sample)
        return spread_sd([counts[d] / n for d in decks])

    deltas = []
    na, nb = len(games_a), len(games_b)
    for _ in range(trials):
        sa = [games_a[rng.randrange(na)] for _ in range(na)]
        sb = [games_b[rng.randrange(nb)] for _ in range(nb)]
        deltas.append(sd_of(sa) - sd_of(sb))
    deltas.sort()
    return {
        "point": sd_of(games_a) - sd_of(games_b),
        "lo": deltas[int(0.025 * (len(deltas) - 1))],
        "hi": deltas[int(0.975 * (len(deltas) - 1))],
        "frac_negative": sum(1 for d in deltas if d < 0) / len(deltas),
    }


def expand(paths):
    out = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(str(x) for x in path.glob("shim_raw_*.jsonl")))
        elif any(ch in p for ch in "*?["):
            out.extend(sorted(glob.glob(p)))
        elif path.exists():
            out.append(str(path))
        else:
            print(f"warn: no such path: {p}", file=sys.stderr)
    return out


def collect(paths):
    """Group every result record by (pod, arm)."""
    cells = defaultdict(lambda: {
        "pod": None, "arm": None, "decks": [], "games": [], "files": [],
    })
    for path in paths:
        meta, results = load_raw(path)
        if meta is None:
            print(f"warn: no meta record, skipping: {path}", file=sys.stderr)
            continue
        pod = pod_key(meta)
        arm = arm_of(meta, path)
        cell = cells[(pod, arm)]
        cell["pod"] = pod
        cell["arm"] = arm
        cell["decks"] = list(pod)
        cell["files"].append(Path(path).name)
        for r in results:
            cell["games"].append({
                "winner": strip_seat(r.get("winner")),
                "draw": bool(r.get("draw")),
                "timed_out": bool(r.get("timedOut")),
                "turns": r.get("turns"),
                "ms": r.get("ms"),
            })
    return cells


def summarize_cell(cell, null_trials):
    games = cell["games"]
    decks = cell["decks"]
    n = len(games)
    timed = [g for g in games if g["timed_out"]]
    clean = [g for g in games if not g["timed_out"] and not g["draw"]]
    other_draws = [g for g in games
                   if g["draw"] and not g["timed_out"]]

    winners = [g["winner"] for g in clean if g["winner"]]
    counts = {d: 0 for d in decks}
    for w in winners:
        if w in counts:
            counts[w] += 1

    nclean = len(winners)
    per_deck = []
    for d in decks:
        k = counts[d]
        rate = k / nclean if nclean else 0.0
        lo, hi = wilson(k, nclean)
        per_deck.append({"deck": d, "wins": k, "rate": rate, "lo": lo, "hi": hi})
    per_deck.sort(key=lambda r: -r["rate"])

    rates = [r["rate"] for r in per_deck]
    sd = spread_sd(rates)
    nul = null_spread(len(decks), nclean, trials=null_trials) if nclean else None

    def secs(g):
        return (g["ms"] or 0) / 1000.0

    natural = [g for g in games if not g["timed_out"] and g["ms"]]
    tps = [g["turns"] / secs(g) for g in natural if g["turns"] and secs(g) > 0]

    # What the old defaults would have done to these same games. A game that ran
    # longer than a hypothetical clock would have been cut and credited to a
    # quasi-arbitrary winner, which is how the pre-fix figures were produced.
    what_if = {}
    if natural:
        for clock in (120, 300, 600):
            cut = sum(1 for g in natural if secs(g) > clock)
            what_if[clock] = {
                "would_be_cut": cut,
                "rate": cut / len(natural),
                "of_natural": len(natural),
            }

    return {
        "what_if_clock": what_if,
        "arm": cell["arm"],
        "decks": decks,
        "files": cell["files"],
        "n_games": n,
        "n_timed_out": len(timed),
        "timeout_rate": len(timed) / n if n else 0.0,
        "n_other_draws": len(other_draws),
        "n_clean": nclean,
        "per_deck": per_deck,
        "spread_sd": sd,
        "spread_range": (max(rates) - min(rates)) if rates else 0.0,
        "null_spread": nul,
        "median_turns": statistics.median([g["turns"] for g in games if g["turns"]]) if games else None,
        "median_secs_natural": statistics.median([secs(g) for g in natural]) if natural else None,
        "median_turns_per_sec": statistics.median(tps) if tps else None,
        "_winners": winners,
    }


def fmt_pct(x):
    return f"{100 * x:5.1f}%"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="raw jsonl files, dirs, or globs")
    ap.add_argument("--json", help="write the full result as JSON here")
    ap.add_argument("--null-trials", type=int, default=20000)
    ap.add_argument("--boot-trials", type=int, default=10000)
    ap.add_argument("--null-only", action="store_true",
                    help="just print the null spread for --decks/--games")
    ap.add_argument("--decks", type=int, default=4)
    ap.add_argument("--games", type=int, default=8)
    ap.add_argument("--label", default="", help="label for the report header")
    args = ap.parse_args()

    if args.null_only:
        nul = null_spread(args.decks, args.games, trials=args.null_trials)
        print(f"Null spread SD, {args.decks} identical decks, {args.games} games:")
        print(f"  mean {fmt_pct(nul['mean'])}   median {fmt_pct(nul['p50'])}"
              f"   95th pct {fmt_pct(nul['p95'])}")
        se = math.sqrt((1 / args.decks) * (1 - 1 / args.decks) / args.games)
        print(f"  per-deck sampling SE at p=1/{args.decks}: {fmt_pct(se)}")
        return 0

    paths = expand(args.paths)
    if not paths:
        ap.error("no input files found")

    cells = collect(paths)
    by_pod = defaultdict(dict)
    for (pod, arm), cell in cells.items():
        by_pod[pod][arm] = summarize_cell(cell, args.null_trials)

    out = {"label": args.label, "pods": []}

    for pod, arms in sorted(by_pod.items()):
        short = [d.split(" [")[0] for d in pod]
        print("=" * 78)
        print("POD: " + " | ".join(short))
        print("=" * 78)

        pod_rec = {"decks": list(pod), "arms": {}}
        for arm in ("stock", "agent"):
            s = arms.get(arm)
            if not s:
                continue
            print(f"\n  arm: {arm}")
            print(f"    games {s['n_games']}  |  timeouts {s['n_timed_out']}"
                  f" ({fmt_pct(s['timeout_rate'])})"
                  f"  |  other draws {s['n_other_draws']}"
                  f"  |  clean {s['n_clean']}")
            if s["median_secs_natural"] is not None:
                print(f"    median natural game {s['median_secs_natural']:.0f} s"
                      f"  |  median turns {s['median_turns']}"
                      f"  |  median turns/sec {s['median_turns_per_sec']:.3f}")
            if s["what_if_clock"]:
                bits = [f"{c} s: {w['would_be_cut']}/{w['of_natural']}"
                        f" ({fmt_pct(w['rate']).strip()})"
                        for c, w in sorted(s["what_if_clock"].items())]
                print("    would have been clock-forced at  " + "   ".join(bits))
            for r in s["per_deck"]:
                name = r["deck"].split(" [")[0][:34]
                print(f"      {name:<34} {r['wins']:>3}/{s['n_clean']:<3}"
                      f" {fmt_pct(r['rate'])}   95% CI"
                      f" [{fmt_pct(r['lo'])},{fmt_pct(r['hi'])}]")
            nul = s["null_spread"]
            print(f"    spread SD {fmt_pct(s['spread_sd'])}"
                  f"  range {fmt_pct(s['spread_range'])}")
            if nul:
                verdict = ("INDISTINGUISHABLE from identical decks"
                           if s["spread_sd"] <= nul["p95"]
                           else "exceeds chance (p<0.05)")
                print(f"    null spread SD at n={s['n_clean']}:"
                      f" mean {fmt_pct(nul['mean'])}, 95th pct {fmt_pct(nul['p95'])}"
                      f"  ->  {verdict}")
            pod_rec["arms"][arm] = {k: v for k, v in s.items() if k != "_winners"}

        if "stock" in arms and "agent" in arms:
            a, b = arms["agent"], arms["stock"]
            boot = bootstrap_delta(a["_winners"], b["_winners"], list(pod),
                                   trials=args.boot_trials)
            print(f"\n  COMPRESSION TEST (agent spread - stock spread)")
            if boot:
                sign = "compression" if boot["point"] < 0 else "expansion"
                print(f"    point {100 * boot['point']:+.1f} pp ({sign})"
                      f"   95% CI [{100 * boot['lo']:+.1f},"
                      f" {100 * boot['hi']:+.1f}] pp")
                crosses = boot["lo"] < 0 < boot["hi"]
                print(f"    P(agent spread < stock spread) ="
                      f" {boot['frac_negative']:.2f}")
                print(f"    verdict: {'NOT SIGNIFICANT (CI spans 0)' if crosses else 'significant'}")
                pod_rec["compression_test"] = boot
            print(f"    timeout rate: stock {fmt_pct(b['timeout_rate'])}"
                  f"  vs agent {fmt_pct(a['timeout_rate'])}")
        print()
        out["pods"].append(pod_rec)

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
