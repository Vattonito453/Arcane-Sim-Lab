#!/usr/bin/env python3
"""Tally an arm's cells into cohort_results.json without waiting for the run.

The runner writes its summary only at the end; this reads whatever cells exist
so a long run can be analysed while it is still going. Winners are mapped to
decks by SEAT, never by name: Ai(n)- also looks like Forge's (123) instance-id
syntax, and precon names repeat across sets.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEAT_RE = re.compile(r"^Ai\((\d+)\)-")
sys.path.insert(0, str(HERE))
from run_cohort import pods_for_round  # noqa: E402


def main(arm="runs_stock"):
    cohort = json.loads((HERE / "cohort.json").read_text(encoding="utf-8"))
    d = HERE / arm
    wins, played, cells, games = {}, {}, 0, 0
    for f in sorted(d.glob("c_r*_p*_i*.jsonl")):
        m = re.match(r"c_r(\d+)_p(\d+)_i(\d+)\.jsonl", f.name)
        if not m:
            continue
        rnd, pod_i, inv = int(m.group(1)), int(m.group(2)), int(m.group(3))
        pods = pods_for_round(cohort, rnd)
        if pod_i >= len(pods):
            continue
        pod = pods[pod_i]
        order = pod[inv:] + pod[:inv]
        seats = [cohort[i]["name"] for i in order]
        cells += 1
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") != "result":
                continue
            games += 1
            for s in seats:
                played[s] = played.get(s, 0) + 1
            w = r.get("winner")
            if r.get("draw") or not w:
                continue
            mm = SEAT_RE.match(w)
            if mm:
                wins[seats[int(mm.group(1)) - 1]] = \
                    wins.get(seats[int(mm.group(1)) - 1], 0) + 1
    recs = [{"name": c["name"], "human": c["human"], "human_n": c["n"],
             "sim_games": played.get(c["name"], 0),
             "sim_wins": wins.get(c["name"], 0),
             "sim_rate": (wins.get(c["name"], 0) / played[c["name"]])
                         if played.get(c["name"]) else None}
            for c in cohort]
    (d / "cohort_results.json").write_text(json.dumps(recs, indent=1), encoding="utf-8")
    got = [r for r in recs if r["sim_games"]]
    gp = sorted(r["sim_games"] for r in got)
    print(f"{arm}: {cells} cells, {games} games, {len(got)}/{len(recs)} decks with data, "
          f"median {gp[len(gp)//2] if gp else 0} games/deck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "runs_stock"))
