#!/usr/bin/env python3
"""E7: after DFC normalisation, do the Ral decks cast their commander?

Pre-registered in PREREG.md (repair plan WS4 task 7, section 4.4 E7). Two
subcommands:

  run      Each Ral deck's own pod, 8 games seat-rotated (run_sim.py --rotate:
           2 games x 4 rotations), stock seats (--agent shim, no plans), both
           pods at once (2 JVMs). run_sim's console output goes to a log file
           under --out and is never printed or read: it lists per-deck wins,
           and CxKMqO36DdM is a holdout pod.
  extract  Reads ONLY the number of games, meta.unsupported_cards, and the Ral
           seat's commander zone records (from Command to Stack or
           Battlefield). Writes <out>/e7_extract.json and prints the per-game
           table and the verdict. Nothing about wins is read.

Raw output stays under --out, a scratch directory; none of it is committed.

    py studies/e7_ral_fidelity/run_e7.py run --out <scratch> --shim-jar <0.16.0 jar>
    py studies/e7_ral_fidelity/run_e7.py extract --out <scratch>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECKS = REPO / "studies" / "human_ceiling" / "decks"

# Seat order as the human_ceiling study ran them (tools/run_queue2.sh).
PODS = {
    "sZA0KqXCGrY": ["joseph_ral.dck", "tyler_bluefarm.dck", "ashton_bluefarm.dck",
                    "natalie_magda.dck"],
    "CxKMqO36DdM": ["dallas_bluefarm.dck", "alan_tnt.dck", "sterling_bluefarm.dck",
                    "joseph_ral.dck"],
}
RAL_SEAT = "joseph_ral"                      # the deck's Name=, Forge's player "Ai(n)-joseph_ral"
RAL_FACES = {"Ral, Monsoon Mage", "Ral, Leyline Prodigy"}
GAMES_PER_POD = 8
PASS_SHARE = 0.70
MIN_GAMES_FOR_VERDICT = 12                   # of 16; below this, re-run the short pod once

# The normalised joseph_ral.dck (identical in both pods), as pre-registered.
RAL_DCK_SHA256 = "9cdd000d7ff1b717f5b514f1f3bf82454ebfb21eb5b2ca0a4a31e33f926ac172"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _strip_seat(player: str) -> str:
    return re.sub(r"^Ai\(\d+\)-", "", player or "")


def run(out: Path, shim_jar: Path, clock: int, max_turns: int) -> None:
    for pod in PODS:
        got = _sha256(DECKS / pod / "dck" / "joseph_ral.dck")
        if got != RAL_DCK_SHA256:
            sys.exit(f"{pod}/joseph_ral.dck is not the pre-registered deck ({got})")
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("MTG_DATA_DIR", str(out / "data"))
    record = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "shim_jar": str(shim_jar), "shim_jar_sha256": _sha256(shim_jar),
              "clock": clock, "max_turns": max_turns, "pods": {}}

    def one(pod: str) -> tuple[str, dict]:
        pod_out = out / pod
        pod_out.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(REPO / "engine" / "run_sim.py"),
               "--decks", *PODS[pod], "--deck-dir", str(DECKS / pod / "dck"),
               "--games", str(GAMES_PER_POD), "--format", "Commander",
               "--agent", "shim", "--shim-jar", str(shim_jar), "--rotate",
               "--clock", str(clock), "--max-turns", str(max_turns),
               "--out", str(pod_out), "--run-id", f"e7_{pod}"]
        t0 = time.time()
        with open(pod_out / "run_sim_console.log", "w", encoding="utf-8") as log:
            rc = subprocess.run(cmd, cwd=str(REPO / "engine"), stdout=log,
                                stderr=subprocess.STDOUT, env=env).returncode
        return pod, {"rc": rc, "seconds": round(time.time() - t0),
                     "decks_sha256": {d: _sha256(DECKS / pod / "dck" / d) for d in PODS[pod]}}

    with ThreadPoolExecutor(max_workers=len(PODS)) as ex:   # 2 JVMs, under the cap of 4
        for pod, info in ex.map(one, PODS):
            record["pods"][pod] = info
    record["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "e7_run.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "pods"}, indent=1))
    for pod, info in record["pods"].items():
        print(f"{pod}: run_sim exit {info['rc']} after {info['seconds']} s")


def extract(out: Path) -> dict:
    rows: list[dict] = []
    pods: dict[str, dict] = {}
    for pod, decks in PODS.items():
        files = sorted((out / pod).glob("sim_*_rotated.json"))
        if not files:
            sys.exit(f"no rotated result for {pod} under {out / pod}")
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        meta = data.get("meta") or {}
        games = data.get("games") or []
        pod_rows = []
        for n, g in enumerate(games):
            zones = g.get("zones")
            if zones is None:
                sys.exit(f"{pod} game {n} carries no zone records: not a shim run")
            ral = [z for z in zones if z.get("card") in RAL_FACES
                   and z.get("from") == "Command"
                   and _strip_seat(z.get("fromPlayer") or "") == RAL_SEAT]
            row = {"pod": pod, "game": n + 1,
                   "casts": sum(1 for z in ral if z.get("to") == "Stack"),
                   "put_onto_battlefield": sum(1 for z in ral if z.get("to") == "Battlefield")}
            row["cast"] = row["casts"] > 0
            pod_rows.append(row)
        rows += pod_rows
        pods[pod] = {"file": files[-1].name, "games": len(games),
                     "games_per_rotation_played": meta.get("games_per_rotation_played"),
                     "incomplete": meta.get("incomplete"),
                     "unsupported_cards": meta.get("unsupported_cards"),
                     "games_cast": sum(r["cast"] for r in pod_rows)}
    n = len(rows)
    cast = sum(r["cast"] for r in rows)
    refused = sorted({c for p in pods.values() for c in (p["unsupported_cards"] or [])})
    unknown = [p for p, v in pods.items() if v["unsupported_cards"] is None]
    if refused or unknown:
        verdict = "INVALID"          # the decks under test are not the decks Forge played
    elif n < MIN_GAMES_FOR_VERDICT:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS" if cast >= math.ceil(PASS_SHARE * n) else "FAIL"
    res = {"games": n, "games_cast": cast, "share": round(cast / n, 3) if n else None,
           "needed": math.ceil(PASS_SHARE * n), "verdict": verdict,
           "refused_cards": refused, "pods": pods, "per_game": rows}
    (out / "e7_extract.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for pod, v in pods.items():
        print(f"{pod}: {v['games']} games, commander cast in {v['games_cast']}, "
              f"refused cards: {v['unsupported_cards']}")
    for r in rows:
        print(f"  {r['pod']} game {r['game']}: casts {r['casts']}, "
              f"put onto battlefield {r['put_onto_battlefield']}")
    print(f"pooled: cast in {cast}/{n} games ({res['share']}); need "
          f"{res['needed']}; verdict {verdict}")
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["run", "extract"])
    ap.add_argument("--out", required=True, help="scratch directory (never in git)")
    ap.add_argument("--shim-jar", help="run: the 0.16.0 shim jar")
    ap.add_argument("--clock", type=int, default=900)
    ap.add_argument("--max-turns", type=int, default=120)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    if a.cmd == "run":
        if not a.shim_jar:
            sys.exit("run needs --shim-jar")
        run(out, Path(a.shim_jar).resolve(), a.clock, a.max_turns)
    else:
        extract(out)


if __name__ == "__main__":
    main()
