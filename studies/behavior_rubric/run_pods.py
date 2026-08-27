#!/usr/bin/env python3
"""Run the plan agent over the 8 cEDH pods that have human traces.

Same decks the humans played and the same decks stock Forge already ran, so
the rubric compares three pilots on one board rather than across formats.
Turn cap on (shim 0.8.0): the wall clock is a hang detector only, so nothing
is censored on how busy the machine is.
"""
from __future__ import annotations
import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SHIM = (r"C:\Users\Vatto\AppData\Local\Temp\claude"
        r"\C--Users-Vatto-Magic-Rules-Engine"
        r"\a04e3d06-be86-4427-832d-102b2608b95f\scratchpad\shim-080.jar")
FORGE = r"C:\Users\Vatto\forge\forge-gui-desktop-2.0.13-jar-with-dependencies.jar"


def cell(spec):
    pod, rot, games, out = spec
    if out.exists() and out.stat().st_size > 0:
        return pod
    decks = sorted((REPO / "studies/human_ceiling/decks" / pod / "dck").glob("*.dck"))
    decks = [str(d.resolve()) for d in decks]
    decks = decks[rot:] + decks[:rot]
    cmd = ["java", "-Xmx3g", "-cp", f"{SHIM}{os.pathsep}{FORGE}",
           "simlab.shim.SimShim", "--decks", *decks,
           "--games", str(games), "--timeout", "2400", "--max-turns", "90",
           "--plans", str((HERE / f"plans_{pod}.json").resolve()),
           "--seat-pilots", ",".join(["plan:SimLabHuman"] * 4),
           "--out", str(out.resolve())]
    subprocess.run(cmd, cwd=os.path.expanduser("~/forge"),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return pod


def main():
    pods = json.loads((HERE / "pods.json").read_text(encoding="utf-8"))
    out_dir = HERE / "runs_agent"
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = [(p, r, 1, out_dir / f"{p}_rot{r}.jsonl") for p in pods for r in range(4)]
    print(f"{len(pods)} pods x 4 seat rotations = {len(specs)} games, "
          f"turn cap 90, clock 2400 (hang detector)", flush=True)
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(cell, specs))
    print("done:", len(list(out_dir.glob('*.jsonl'))), "cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
