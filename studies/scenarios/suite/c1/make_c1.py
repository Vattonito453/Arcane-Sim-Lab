#!/usr/bin/env python3
"""C1, the positive control: 20 real stock-game boards with Helm of the Host
attached to Godo, Bandit Warlord before combat on Godo's turn.

    py studies/scenarios/suite/c1/make_c1.py [--runs-root DIR]

Source population: the diagnosis's Helm rows
(studies/diagnosis_2026-09/verify/helm_rows.json), which list every seat-game
in the study corpus where Helm and Godo shared a controller. The plan's
"28/32" comes from them (pooled pilots, games with 4+ combats). Here:

  1. keep rows whose Godo seat was piloted by stock Forge and where Helm got
     attached to Godo ("cat" == godo): 31 seat-games, all on pod 2iA_Jt0d6sM;
  2. find the first attach record; keep attaches made in the precombat main
     phase (MAIN1), because a board seeded at MAIN1 can only reproduce those
     (an attach in MAIN2 has no Helm trigger until the next turn): 23;
  3. draw 20 of the 23 with random.Random(SEED).sample, fixed before any C1
     trial ran;
  4. write each board with board_from_game.py at the attach turn, plus the
     game's own outcome from that board (sources.json) for the paired
     comparison in BASELINE.md.

The raw game JSONL is gitignored (studies/agent_viability/runs_*/cell_*.jsonl);
pass --runs-root to the checkout that holds it.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1]))
import board_from_game as B  # noqa: E402

SEED = 2026101500
N = 20
HORIZON = 8
GODO, HELM = "Godo, Bandit Warlord", "Helm of the Host"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-root", default=str(REPO / "studies"),
                    help="the studies/ folder that holds agent_viability/runs_*/cell_*.jsonl")
    ap.add_argument("--forge-index", help="Forge index cards.json (double-faced cards on their back face)")
    args = ap.parse_args()
    root = Path(args.runs_root)
    index = Path(args.forge_index) if args.forge_index else None
    rows = json.loads((REPO / "studies/diagnosis_2026-09/verify/helm_rows.json").read_text(encoding="utf-8"))
    pool = []
    for d, f, g, seat, agent, cat, maxc, won in rows:
        if agent != "stock" or cat != "godo":
            continue
        path = root / Path(f.replace("\\", "/"))
        meta, recs = B.load_game(path, g)
        owners = {}
        for r in recs:
            if r.get("rec") == "entry" and r.get("type") == "TURN":
                m = B.TURN.match(r.get("message", ""))
                if m:
                    owners[int(m.group(1))] = m.group(2)
        att = next((r for r in recs if r.get("rec") == "attach" and r.get("card") == HELM
                    and r.get("to") == GODO), None)
        res = next((r for r in recs if r.get("rec") == "result"), None)
        if att is None or res is None:
            continue
        turn = int(att["turn"])
        pool.append({"file": Path(f.replace("\\", "/")).as_posix(), "game": g, "seat": seat,
                     "turn": turn, "phase": att.get("phase"), "own_turn": owners.get(turn) == seat,
                     "max_combats_any_turn": maxc, "won": bool(won), "end_turn": res.get("turns"),
                     "won_on_attach_turn": bool(won) and res.get("turns") == turn,
                     "won_within_horizon": bool(won) and res.get("turns") is not None
                     and res.get("turns") <= turn + HORIZON})
    main1 = [p for p in pool if p["phase"] == "MAIN1" and p["own_turn"]]
    print(f"stock Helm-on-Godo seat-games: {len(pool)}; attached in MAIN1 on Godo's turn: {len(main1)}")
    chosen = random.Random(SEED).sample(sorted(main1, key=lambda p: (p["file"], p["game"])), N)
    chosen.sort(key=lambda p: (p["file"], p["game"]))
    out = []
    for p in chosen:
        run = p["file"].split("/")[-2].replace("runs_", "")
        rot = re.search(r"rot(\d)", p["file"]).group(1)
        sid = f"c1_{run}_r{rot}_g{p['game']:02d}"
        sc = B.build(root / p["file"], p["game"], p["turn"], sid, None, index)
        seat = sc["active"]
        sc["description"] = (
            "C1 positive control. A real stock game's board at the moment Helm of the Host sat on Godo, "
            "Bandit Warlord before combat on Godo's turn; every seat stock in the stock arm. Forge alone "
            "converted boards like this in games; the harness must not change that.")
        sc["success"] = {"type": "win", "seat": seat, "by_turn": p["turn"] + HORIZON}
        sc["line"] = {"seat": seat, "pieces": [GODO, HELM]}
        sc["horizon_turns"] = HORIZON
        (HERE / f"{sid}.json").write_text(json.dumps(sc, indent=1) + "\n", encoding="utf-8")
        out.append(dict(p, id=sid))
        print(f"{sid}: turn {p['turn']}, in game won={p['won']} same turn={p['won_on_attach_turn']} "
              f"within {HORIZON}={p['won_within_horizon']}")
    summary = {"seed": SEED, "population_stock_attached": len(pool), "population_main1": len(main1),
               "chosen": out,
               "in_game": {"won": sum(p["won"] for p in out),
                           "won_on_attach_turn": sum(p["won_on_attach_turn"] for p in out),
                           "won_within_horizon": sum(p["won_within_horizon"] for p in out),
                           "reached_4_combats": sum(p["max_combats_any_turn"] >= 4 for p in out)},
               "not_chosen": [dict(p) for p in main1 if p not in chosen]}
    (HERE / "sources.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary["in_game"]))


if __name__ == "__main__":
    main()
