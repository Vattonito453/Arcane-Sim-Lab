#!/usr/bin/env python3
"""Run headless Forge Commander simulations and emit game_log-schema JSON.

Usage:
  python3 run_sim.py --decks deckA.dck deckB.dck deckC.dck deckD.dck \
      --games 25 --format Commander --out ./sim_results

Forge discovery order: --forge-jar flag, FORGE_JAR env var, then common
install locations. Install Forge with ../engine/setup_forge.sh first.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from forge_log_adapter import parse_forge_log

FORGE_SEARCH_GLOBS = [
    "~/forge/forge-gui-desktop-*-jar-with-dependencies.jar",
    "~/forge/*.jar",
    "/opt/forge/forge-gui-desktop-*-jar-with-dependencies.jar",
    "~/Forge/forge-gui-desktop-*.jar",
]


def find_forge_jar(explicit: str | None) -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("FORGE_JAR"):
        candidates.append(os.environ["FORGE_JAR"])
    for pattern in FORGE_SEARCH_GLOBS:
        candidates.extend(sorted(glob.glob(os.path.expanduser(pattern)), reverse=True))
    for c in candidates:
        if c and Path(os.path.expanduser(c)).is_file():
            return os.path.expanduser(c)
    sys.exit("Forge jar not found. Run setup_forge.sh, or pass --forge-jar / set FORGE_JAR.")


def forge_profile_deck_dir(fmt: str) -> Path:
    """Forge's own deck folder. In plain -d mode Forge ONLY loads .dck files
    from here (the -D flag is honored in tournament mode only — verified in
    SimulateMatch.java, Forge 2.0.13)."""
    if os.environ.get("FORGE_USER_DIR"):
        base = Path(os.environ["FORGE_USER_DIR"])
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Forge"
    elif platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home())) / "Forge"
    else:
        base = Path.home() / ".forge"
    sub = "commander" if fmt.lower() == "commander" else "constructed"
    return base / "decks" / sub


def stage_decks(decks: list[str], deck_dir: str | None, fmt: str) -> None:
    """Copy .dck files into Forge's profile deck folder so -d can find them."""
    target = forge_profile_deck_dir(fmt)
    target.mkdir(parents=True, exist_ok=True)
    for d in decks:
        if not d.endswith(".dck"):
            continue  # a deck *name* already known to Forge's deck store
        src = Path(os.path.expanduser(deck_dir or ".")) / d if not os.path.isabs(d) else Path(d)
        if src.is_file():
            shutil.copy2(src, target / Path(d).name)
            print(f"staged {src.name} -> {target}")
        elif not (target / Path(d).name).is_file():
            sys.exit(f"deck file not found: {src}")


def run(args: argparse.Namespace) -> None:
    jar = find_forge_jar(args.forge_jar)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    stage_decks(args.decks, args.deck_dir, args.format)
    deck_names = [Path(d).name for d in args.decks]

    if args.rotate:
        # Forge's AI has a strong seat bias (measured: seat 1 wins ~11%, seat 4
        # ~36%). Rotate deck order across sub-runs so every deck sits in every
        # seat, then merge results (players are identified by deck name).
        rotations = len(deck_names)
        per = max(1, args.games // rotations)
        all_games = []
        for i in range(rotations):
            order = deck_names[i:] + deck_names[:i]
            print(f"\n--- rotation {i+1}/{rotations}: seats = {order} ---")
            sub = _run_once(args, jar, out_dir, order, per)
            all_games.extend(sub["games"])
        result = {"meta": {"source": "rotated", "decks": args.decks,
                           "format": args.format, "rotations": rotations},
                  "games": all_games, "summary": _summarize_by_deck(all_games)}
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = out_dir / f"sim_{stamp}_rotated.json"
        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        s = result["summary"]
        print(f"\n{s['games']} game(s) total across {rotations} seat rotations | draws: {s['draws']}")
        for player, rate in sorted(s["win_rates"].items(), key=lambda kv: -kv[1]):
            print(f"  {player}: {s['wins'][player]} wins ({rate:.0%})")
        print(f"json    : {json_path}")
        return

    cmd = ["java", f"-Xmx{args.heap}", "-jar", jar, "sim", "-d", *deck_names]
    cmd += ["-f", args.format, "-n", str(args.games), "-c", str(args.clock)]
    if args.quiet:
        cmd += ["-q"]

    print("$", " ".join(cmd))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # With --run-id the log is addressable while it is still being written, which
    # is what lets GET /sim-live parse the game in progress. Without one, keep the
    # timestamped name so nothing else changes.
    raw_path = out_dir / (f"forge_raw_{args.run_id}.log" if args.run_id
                          else f"forge_raw_{stamp}.log")

    # Stream Forge's output live: show progress lines on screen, save everything.
    stdout_lines: list[str] = []
    turn_count = 0
    # Forge must run from its install dir so it finds the res/ folder.
    proc = subprocess.Popen(cmd, cwd=Path(jar).parent, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    # buffering=1 (line buffered): a reader tailing this file has to see turns as
    # they happen, not in 8 KB bursts.
    with open(raw_path, "w", encoding="utf-8", buffering=1) as rawf:
        assert proc.stdout is not None
        for line in proc.stdout:
            rawf.write(line)
            stdout_lines.append(line)
            s = line.strip()
            if s.startswith("Turn:"):
                turn_count += 1
                if turn_count % 10 == 0:
                    print(f"  ... {turn_count} player-turns played", flush=True)
            elif s.startswith(("Game Result", "Match", "Simulation mode", "Stopping slow match")) \
                    or "vs " in s and s.endswith("Commander"):
                print(f"  {s}", flush=True)
    proc.wait(timeout=60)

    result = parse_forge_log("".join(stdout_lines), source=" ".join(cmd))
    result["meta"]["decks"] = args.decks
    result["meta"]["format"] = args.format
    json_path = out_dir / f"sim_{stamp}.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s = result["summary"]
    print(f"\n{s['games']} game(s) parsed | draws: {s['draws']}")
    for player, rate in sorted(s["win_rates"].items(), key=lambda kv: -kv[1]):
        print(f"  {player}: {s['wins'][player]} wins ({rate:.0%})")
    print(f"\nraw log : {raw_path}\njson    : {json_path}")
    if proc.returncode != 0:
        print(f"WARNING: Forge exited {proc.returncode} — check the raw log.", file=sys.stderr)


def _run_once(args, jar, out_dir, deck_order, games) -> dict:
    """One Forge invocation with a fixed seat order; returns parsed result."""
    cmd = ["java", f"-Xmx{args.heap}", "-jar", jar, "sim", "-d", *deck_order]
    cmd += ["-f", args.format, "-n", str(games), "-c", str(args.clock)]
    print("$", " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=Path(jar).parent, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        if line.strip().startswith("Game Result"):
            print("  " + line.strip(), flush=True)
    proc.wait(timeout=60)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    (out_dir / f"forge_raw_{stamp}.log").write_text("".join(lines), encoding="utf-8")
    return parse_forge_log("".join(lines), source=" ".join(cmd))


def _summarize_by_deck(games: list) -> dict:
    """Aggregate wins by DECK (strip the Ai(n)- seat prefix)."""
    import re as _re
    seat = _re.compile(r"^Ai\(\d+\)-")   # \d+ — a 10-seat pod is still Ai(10)-
    wins: dict = {}
    draws = 0
    # Every deck in the pod gets a key, winless or not: these keys are the pod
    # roster for everything downstream, including the even-seats baseline.
    for g in games:
        for p in g.get("players") or []:
            wins.setdefault(seat.sub("", p), 0)
    for g in games:
        r = g.get("result") or {}
        if r.get("draw"):
            draws += 1
        elif r.get("winner"):
            name = seat.sub("", r["winner"])
            wins[name] = wins.get(name, 0) + 1
    total = len(games)
    return {"games": total, "draws": draws, "wins": wins,
            "win_rates": {p: round(w / total, 3) for p, w in wins.items()} if total else {}}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--decks", nargs="+", required=True,
                   help=".dck filenames (or deck names known to Forge). 4 decks = 4-player pod.")
    p.add_argument("--deck-dir", default=None, help="Directory containing the .dck files (-D)")
    p.add_argument("--games", type=int, default=10)
    p.add_argument("--format", default="Commander")
    p.add_argument("--clock", type=int, default=120, help="Per-game timeout seconds (draw when exceeded)")
    p.add_argument("--quiet", action="store_true", help="Result-only logs (no per-action events)")
    p.add_argument("--forge-jar", default=None)
    p.add_argument("--heap", default="4g", help="JVM max heap (default 4g)")
    p.add_argument("--rotate", action="store_true",
                   help="Rotate seat order across sub-runs to cancel Forge's seat bias (recommended for 4-player)")
    p.add_argument("--out", default="./sim_results")
    p.add_argument("--run-id", default=None,
                   help="Job id. Names the raw log forge_raw_<id>.log so the API "
                        "can read the game in progress (GET /sim-live).")
    run(p.parse_args())


if __name__ == "__main__":
    main()
