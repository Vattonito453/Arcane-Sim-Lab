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
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from forge_log_adapter import parse_forge_log

FORGE_SEARCH_GLOBS = [
    "~/forge/forge-gui-desktop-*-jar-with-dependencies.jar",
    "~/forge/*.jar",
    "/opt/forge/forge-gui-desktop-*-jar-with-dependencies.jar",
    "~/Forge/forge-gui-desktop-*.jar",
]

# The GPL shim (separate repo — see CLAUDE.md "Legal posture") that drives
# Forge programmatically and emits typed logs + zone ground truth.
SHIM_SEARCH_GLOBS = [
    "~/Desktop/Personal/simlab-forge-shim/simlab-forge-shim.jar",
    "/opt/simlab-forge-shim/simlab-forge-shim.jar",
]


class SimRotationError(RuntimeError):
    """One rotation failed. Carries whatever games it finished first.

    Raised instead of warning, because the merged result has to be able to say
    a rotation is missing (audit A5). The partial games are still good games
    and are kept; what must not happen is a short run presenting itself as a
    complete one.
    """

    def __init__(self, message: str, partial: dict | None = None) -> None:
        super().__init__(message)
        self.partial = partial or {}


def find_shim_jar(explicit: str | None, required: bool = True) -> str | None:
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("SIMLAB_SHIM_JAR"):
        candidates.append(os.environ["SIMLAB_SHIM_JAR"])
    for pattern in SHIM_SEARCH_GLOBS:
        candidates.extend(sorted(glob.glob(os.path.expanduser(pattern)), reverse=True))
    for c in candidates:
        if c and Path(os.path.expanduser(c)).is_file():
            return os.path.expanduser(c)
    if required:
        sys.exit("shim jar not found. Build simlab-forge-shim (./build.sh), or pass "
                 "--shim-jar / set SIMLAB_SHIM_JAR.")
    return None


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


def platform_profile_base() -> Path:
    """Where Forge itself keeps its profile on this OS."""
    if os.environ.get("FORGE_USER_DIR"):
        return Path(os.environ["FORGE_USER_DIR"])
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Forge"
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", Path.home())) / "Forge"
    return Path.home() / ".forge"


# ── Forge profile isolation ──────────────────────────────────────────────
# Staged decks used to land in ONE folder shared by every process on the box,
# keyed by bare filename. Two concurrent sims then clobber each other: worker
# B stages its own "kilo_helm.dck" over worker A's copy between A's rotations,
# and A finishes reporting results under a deck name it never actually played.
# Nothing downstream can detect that, which is what makes it dangerous.
#
# The shim (the product default) takes ABSOLUTE .dck paths, so it does not care
# where the staging folder lives — give each invocation its own and the whole
# class of collision disappears. Stock Forge's `sim -d` resolves deck NAMES out
# of Forge's real profile, so that path has to keep using the shared folder;
# _init_profile refuses to isolate it rather than silently staging somewhere
# Forge will never look. studies/precon_correlation/run_study.py pins
# FORGE_USER_DIR per worker and is honored as-is.
_PROFILE_BASE: Path | None = None
_PROFILE_IS_PRIVATE = False


def sweep_stale_profiles(root: Path, max_age_h: float = 24.0) -> int:
    """Delete private profiles a killed run never cleaned up."""
    if not root.is_dir():
        return 0
    cutoff = time.time() - max_age_h * 3600
    removed = 0
    for p in root.iterdir():
        try:
            if p.is_dir() and p.stat().st_mtime < cutoff:
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        except OSError:
            pass  # another worker swept it first, or it is busy; not our problem
    return removed


def _init_profile(agent: str, run_id: str | None) -> None:
    """Pick this invocation's staging root. Call once, before stage_decks."""
    global _PROFILE_BASE, _PROFILE_IS_PRIVATE
    if os.environ.get("FORGE_USER_DIR") or agent != "shim":
        # Caller pinned it, or stock Forge needs its own profile to resolve -d.
        _PROFILE_BASE, _PROFILE_IS_PRIVATE = platform_profile_base(), False
        return
    root = platform_profile_base() / "simlab-runs"
    root.mkdir(parents=True, exist_ok=True)
    sweep_stale_profiles(root)
    # mkdtemp, not run_id alone: a retried job reuses its id, and two live runs
    # must never share a folder even then.
    _PROFILE_BASE = Path(tempfile.mkdtemp(prefix=f"{run_id or os.getpid()}-", dir=root))
    _PROFILE_IS_PRIVATE = True


def _cleanup_profile() -> None:
    if _PROFILE_IS_PRIVATE and _PROFILE_BASE:
        shutil.rmtree(_PROFILE_BASE, ignore_errors=True)


def forge_profile_deck_dir(fmt: str) -> Path:
    """Forge's own deck folder. In plain -d mode Forge ONLY loads .dck files
    from here (the -D flag is honored in tournament mode only — verified in
    SimulateMatch.java, Forge 2.0.13)."""
    base = _PROFILE_BASE or platform_profile_base()
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
        if not src.is_file():
            # Never fall through to a copy some earlier run staged. That used to
            # be a silent success that simmed a stale decklist under the right
            # name -- e.g. a deck edited or deleted after the job was queued.
            sys.exit(f"deck file not found: {src}")
        shutil.copy2(src, target / Path(d).name)
        print(f"staged {src.name} -> {target}")


def _run_shim_once(args, jar: str, shim_jar: str, out_dir: Path,
                   deck_order: list[str], games: int,
                   rotate_index: int | None = None) -> dict:
    """One shim invocation with a fixed seat order; returns parsed result.

    Decks must already be staged (the shim takes absolute .dck paths; the
    staged copies in Forge's profile deck dir are the canonical ones).

    rotate_index, when set, names the live log <run_id>_rot<i> instead of
    dropping run_id altogether — GET /sim-live globs for that suffix so
    watching a rotated run (the default) doesn't go dark for its whole
    duration. See mtg_engine.py _read_live."""
    from shim_log_adapter import parse_shim_jsonl
    staged = forge_profile_deck_dir(args.format)
    abs_decks = [str(staged / Path(d).name) for d in deck_order]
    if args.run_id:
        suffix = f"_rot{rotate_index}" if rotate_index is not None else ""
        jsonl_path = out_dir / f"shim_raw_{args.run_id}{suffix}.jsonl"
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        jsonl_path = out_dir / f"shim_raw_{stamp}.jsonl"
    cmd = ["java", f"-Xmx{args.heap}", "-cp", f"{shim_jar}{os.pathsep}{jar}",
           "simlab.shim.SimShim", "--decks", *abs_decks,
           "--games", str(games), "--timeout", str(args.clock),
           "--out", str(jsonl_path)]
    if getattr(args, "plans_file", None):
        cmd += ["--plans", str(args.plans_file)]
    print("$", " ".join(cmd))
    # Forge must run from its install dir so it finds the res/ folder.
    proc = subprocess.Popen(cmd, cwd=Path(jar).parent, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    assert proc.stderr is not None
    for line in proc.stderr:  # shim progress arrives on stderr
        s = line.strip()
        if s.startswith("shim:"):
            print(f"  {s}", flush=True)
    proc.wait(timeout=60)
    parsed = parse_shim_jsonl(jsonl_path.read_text(encoding="utf-8"),
                              source=" ".join(cmd))
    if proc.returncode != 0:
        # A warning on stderr was the whole response to this, so a rotation
        # that OOM'd halfway still merged its partial games into a result
        # claiming a full rotation (audit A5). Salvage whatever games the
        # rotation did finish, then fail so the caller records the hole.
        raise SimRotationError(
            f"shim exited {proc.returncode} after {len(parsed.get('games') or [])} "
            f"game(s)", partial=parsed)
    return parsed


def run(args: argparse.Namespace) -> None:
    jar = find_forge_jar(args.forge_jar)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Agent resolution. "auto" (the default) means HUMANIZED — that is the
    # product: plan agents whenever the shim jar is available, with a loud,
    # labeled fallback to stock Forge when it is not (a machine without the
    # shim should still sim, but never silently pretend to be humanized).
    #
    # Resolved BEFORE staging because it decides where staging is allowed to
    # go: the shim reads absolute .dck paths and can use a private folder,
    # stock Forge cannot (see _init_profile).
    if args.agent == "auto":
        if find_shim_jar(args.shim_jar, required=False):
            args.agent = "shim"
            args.humanize = True
        else:
            print("WARNING: shim jar not found — falling back to STOCK Forge AI. "
                  "Results will carry humanized:false. Build simlab-forge-shim "
                  "and/or set SIMLAB_SHIM_JAR to restore the default agent.",
                  file=sys.stderr)
            args.agent = "forge"
            args.humanize = False
    elif args.humanize:
        args.agent = "shim"  # plan agents only exist behind the shim

    _init_profile(args.agent, args.run_id)
    if not _PROFILE_IS_PRIVATE and args.agent != "shim":
        print("NOTE: stock Forge resolves decks from its shared profile, so this "
              "run stages into a folder other sims also write. Do not run stock "
              "sims concurrently on one machine.", file=sys.stderr)
    stage_decks(args.decks, args.deck_dir, args.format)
    deck_names = [Path(d).name for d in args.decks]

    if args.agent == "shim":
        shim_jar = find_shim_jar(args.shim_jar)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.plans_file = None
        if args.humanize:
            # Deck plans are OUR strategy data; they cross to the GPL shim
            # as JSON (CLAUDE.md legal posture — the boundary is the design).
            from deck_plan import build_plans
            staged = forge_profile_deck_dir(args.format)
            plans = build_plans([staged / Path(d).name for d in deck_names])
            # The id, not just the timestamp: the stamp has one-second
            # resolution, so concurrent workers collided on this filename and
            # one silently overwrote the other's plans. The loser's shim then
            # read a plans file describing a DIFFERENT pod -- the three shared
            # control decks matched, its own deck did not, and that deck ran
            # stock AI in a run still labeled humanized. That is what corrupted
            # half the agent arm of the precon pilot.
            tag = f"_{safe_run_id(args.run_id)}" if args.run_id else f"_pid{os.getpid()}"
            args.plans_file = out_dir / f"plans_{stamp}{tag}.json"
            args.plans_file.write_text(json.dumps(plans, indent=2), encoding="utf-8")
            print(f"plans   : {args.plans_file} "
                  f"({', '.join(plans['decks'])})")
            if len(plans["decks"]) < len(deck_names):
                print(f"WARNING: built {len(plans['decks'])} plans for "
                      f"{len(deck_names)} decks — duplicate deck names collapse "
                      f"in the plan map. The shim will refuse the run.",
                      file=sys.stderr)
        if args.rotate:
            rotations = len(deck_names)
            split = plan_games(args.games, rotations)
            all_games = []
            sub_humanized: list[bool] = []
            played_per_rotation: list[int] = []
            for i, per in enumerate(split):
                order = deck_names[i:] + deck_names[:i]
                print(f"\n--- rotation {i+1}/{rotations}: seats = {order} ---")
                try:
                    sub = _run_shim_once(args, jar, shim_jar, out_dir, order, per,
                                         rotate_index=i)
                except SimRotationError as e:
                    # One rotation dying used to be a stderr line and nothing
                    # else: the merged file still claimed rotations:4 and full
                    # bias cancellation. Keep the games it finished, and record
                    # the hole (audit A5).
                    print(f"ERROR: rotation {i+1}/{rotations} failed: {e}",
                          file=sys.stderr)
                    salvaged = e.partial.get("games") or []
                    all_games.extend(salvaged)
                    played_per_rotation.append(len(salvaged))
                    sub_humanized.append(bool(e.partial.get("meta", {}).get("humanized")))
                    continue
                all_games.extend(sub["games"])
                played_per_rotation.append(len(sub["games"]))
                sub_humanized.append(bool(sub.get("meta", {}).get("humanized")))
            result = {"meta": {"source": "rotated", "agent": "simlab-forge-shim",
                               # What the run WAS, not what was asked for. This
                               # used to echo the --humanize flag, so a rotation
                               # whose seats fell back to stock still reported
                               # humanized:true.
                               "humanized": bool(sub_humanized) and all(sub_humanized),
                               "humanized_by_rotation": sub_humanized,
                               "decks": args.decks, "format": args.format,
                               "rotations": rotations,
                               **_rotation_meta(args.games, split, played_per_rotation)},
                      "games": all_games, "summary": _summarize_by_deck(all_games)}
            json_path = result_path(out_dir, stamp, args.run_id, rotated=True)
        else:
            result = _run_shim_once(args, jar, shim_jar, out_dir, deck_names, args.games)
            result["meta"]["decks"] = args.decks
            result["meta"]["format"] = args.format
            json_path = result_path(out_dir, stamp, args.run_id, rotated=False)
        # The per-game wall the run actually used. Without it, a later
        # validity check has to GUESS which clock a file ran under
        # (validity.py _HISTORICAL_CLOCKS) and can only say "suspect".
        result.setdefault("meta", {})["clock"] = args.clock
        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        s = result["summary"]
        print(f"\n{s['games']} game(s) parsed | draws: {s['draws']}")
        for player, rate in sorted(s["win_rates"].items(), key=lambda kv: -kv[1]):
            print(f"  {player}: {s['wins'][player]} wins ({rate:.0%})")
        print(f"json    : {json_path}")
        return

    if args.rotate:
        # Rotate deck order across sub-runs so every deck sits in every seat,
        # then merge results (players are identified by deck name).
        #
        # This comment used to justify rotation with "seat 1 wins ~11%, seat 4
        # ~36%", a 25 pp spread. That figure does NOT reproduce. Measured over
        # 1254 decided games with decks and arms balanced across seats
        # (studies/skill_headtohead/RESULTS.md): 26.4/24.8/24.2/24.6% in
        # heterogeneous pods, a 2.2 pp spread, and 6.4 pp in mirror pods. Both
        # are an order of magnitude below the old claim.
        #
        # Rotation stays regardless: it is nearly free, and balance is what
        # makes a seat effect a non-issue instead of an assumption. But do not
        # cite 11%/36% as evidence for anything. Whatever produced it was a
        # different configuration or too small a sample, and it needs
        # re-measuring before it is relied on again.
        rotations = len(deck_names)
        split = plan_games(args.games, rotations)
        all_games = []
        played_per_rotation: list[int] = []
        for i, per in enumerate(split):
            order = deck_names[i:] + deck_names[:i]
            print(f"\n--- rotation {i+1}/{rotations}: seats = {order} ---")
            try:
                sub = _run_once(args, jar, out_dir, order, per, rotate_index=i)
            except SimRotationError as e:
                print(f"ERROR: rotation {i+1}/{rotations} failed: {e}", file=sys.stderr)
                salvaged = e.partial.get("games") or []
                all_games.extend(salvaged)
                played_per_rotation.append(len(salvaged))
                continue
            all_games.extend(sub["games"])
            played_per_rotation.append(len(sub["games"]))
        result = {"meta": {"source": "rotated", "humanized": False,
                           "decks": args.decks,
                           "format": args.format, "rotations": rotations,
                           **_rotation_meta(args.games, split, played_per_rotation)},
                  "games": all_games, "summary": _summarize_by_deck(all_games)}
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = result_path(out_dir, stamp, args.run_id, rotated=True)
        # The per-game wall the run actually used. Without it, a later
        # validity check has to GUESS which clock a file ran under
        # (validity.py _HISTORICAL_CLOCKS) and can only say "suspect".
        result.setdefault("meta", {})["clock"] = args.clock
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
    result["meta"]["humanized"] = False
    json_path = result_path(out_dir, stamp, args.run_id, rotated=False)
    result.setdefault("meta", {})["clock"] = args.clock
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s = result["summary"]
    print(f"\n{s['games']} game(s) parsed | draws: {s['draws']}")
    for player, rate in sorted(s["win_rates"].items(), key=lambda kv: -kv[1]):
        print(f"  {player}: {s['wins'][player]} wins ({rate:.0%})")
    print(f"\nraw log : {raw_path}\njson    : {json_path}")
    if proc.returncode != 0:
        print(f"WARNING: Forge exited {proc.returncode} — check the raw log.", file=sys.stderr)


def _run_once(args, jar, out_dir, deck_order, games, rotate_index: int | None = None) -> dict:
    """One Forge invocation with a fixed seat order; returns parsed result.

    rotate_index, when set alongside --run-id, names the raw log
    <run_id>_rot<i> so GET /sim-live can glob for the in-flight rotation
    (see _run_shim_once's identical concern for the humanized path)."""
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
    if args.run_id:
        suffix = f"_rot{rotate_index}" if rotate_index is not None else ""
        raw_path = out_dir / f"forge_raw_{args.run_id}{suffix}.log"
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        raw_path = out_dir / f"forge_raw_{stamp}.log"
    raw_path.write_text("".join(lines), encoding="utf-8")
    parsed = parse_forge_log("".join(lines), source=" ".join(cmd))
    if proc.returncode != 0:
        # This path never checked the return code at all, so a rotation Forge
        # aborted contributed however many games it managed and the merged
        # result still claimed a clean sweep (audit A5).
        raise SimRotationError(
            f"Forge exited {proc.returncode} after "
            f"{len(parsed.get('games') or [])} game(s)", partial=parsed)
    return parsed


def salvage(out_dir: Path, run_id: str, decks: list[str] | None = None,
            fmt: str = "Commander", clock: int | None = None,
            games_expected: int | None = None) -> Path | None:
    """Rebuild a result from a killed run's rotation logs. Returns the path.

    The outer kill (Engine.simulate) used to discard everything: run_sim only
    writes the merged result after the LAST rotation, so a run killed in
    rotation 4 threw away three completed rotations that were sitting finished
    on disk (audit A14). Those raw logs are the same files the adapters read at
    the end of a normal run, so recovering them is a re-parse, not a repair.

    The result is marked `incomplete` and `salvaged_from_kill`, which keeps it
    out of anything that ranks decks (validity.py) while still giving the user
    the games their run actually played.
    """
    rid = safe_run_id(run_id)
    games: list = []
    per_rotation: list[int] = []
    humanized: list[bool] = []
    agent = None

    shim_logs = sorted(out_dir.glob(f"shim_raw_{rid}_rot*.jsonl")) or \
        sorted(out_dir.glob(f"shim_raw_{rid}.jsonl"))
    stock_logs = sorted(out_dir.glob(f"forge_raw_{rid}_rot*.log")) or \
        sorted(out_dir.glob(f"forge_raw_{rid}.log"))

    if shim_logs:
        from shim_log_adapter import parse_shim_jsonl
        agent = "simlab-forge-shim"
        for p in shim_logs:
            try:
                sub = parse_shim_jsonl(p.read_text(encoding="utf-8", errors="replace"),
                                       source=p.name)
            except Exception:  # noqa: BLE001 — a torn log loses one rotation, not all
                per_rotation.append(0)
                continue
            # Only games that actually finished: the rotation in flight when
            # the kill landed has a trailing game with no result.
            done = [g for g in (sub.get("games") or []) if g.get("result")]
            games.extend(done)
            per_rotation.append(len(done))
            humanized.append(bool(sub.get("meta", {}).get("humanized")))
    elif stock_logs:
        agent = "forge"
        for p in stock_logs:
            try:
                sub = parse_forge_log(p.read_text(encoding="utf-8", errors="replace"),
                                      source=p.name)
            except Exception:  # noqa: BLE001
                per_rotation.append(0)
                continue
            done = [g for g in (sub.get("games") or []) if g.get("result")]
            games.extend(done)
            per_rotation.append(len(done))

    if not games:
        return None

    # Rotations the run was SUPPOSED to do, not the number of log files that
    # happen to exist. Counting the survivors would report "2 of 2 rotations
    # finished" for a run that lost half of them, which is the opposite of
    # what a salvaged result needs to say.
    rotations_expected = len(decks) if decks else len(per_rotation)
    meta = {
        "source": "rotated" if rotations_expected > 1 else "salvaged",
        "agent": agent,
        "decks": decks or [],
        "format": fmt,
        "rotations": rotations_expected,
        "rotations_completed": sum(1 for n in per_rotation if n > 0),
        "games_played": len(games),
        "games_per_rotation_played": per_rotation,
        "incomplete": True,
        "salvaged_from_kill": True,
    }
    if games_expected:
        meta["games_expected"] = games_expected
    if clock is not None:
        meta["clock"] = clock
    if humanized:
        meta["humanized"] = all(humanized)
        meta["humanized_by_rotation"] = humanized
    result = {"meta": meta, "games": games, "summary": _summarize_by_deck(games)}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = result_path(out_dir, stamp, run_id, rotated=len(per_rotation) > 1)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path


def safe_run_id(run_id: str) -> str:
    """Filename-safe form of a job id. The API's ids are already
    [A-Za-z0-9_-]; a hand-run --run-id is not guaranteed to be."""
    return re.sub(r"[^A-Za-z0-9-]", "", run_id)[:64]


def result_path(out_dir: Path, stamp: str, run_id: str | None, rotated: bool) -> Path:
    """Name the result file so its owning job is readable from the name.

    The engine used to claim a result as "the newest sim_*.json written since I
    started", which credits whichever file lands first — a second worker's, a
    manual run's, a duplicate job's — to this job, and marks it done with
    someone else's numbers. The raw logs have carried the run id all along;
    now the result does too, in its own underscore slot between the timestamp
    and the _rotated suffix. Files written without an id still match the old
    shape, so historical results keep parsing.
    """
    tag = f"_{safe_run_id(run_id)}" if run_id else ""
    return out_dir / f"sim_{stamp}{tag}{'_rotated' if rotated else ''}.json"


def plan_games(requested: int, rotations: int, cap: int | None = None) -> list[int]:
    """Games per rotation, balanced (audit A27).

    Seat rotation only cancels Forge's seat bias if every deck sits in every
    seat the SAME number of times, so the split has to be even. The old
    `per = max(1, games // rotations)` was neither even nor honest about the
    total: 1 requested became 4 played, 6 became 4, 10 (the worker default)
    became 8, and 63 became 60, with the run page showing the request and the
    result file showing something else.

    Rounding UP to a whole rotation is the choice here, over distributing the
    remainder. Distributing it (6 over 4 seats = 2,2,1,1) leaves two decks with
    an extra game in an early seat, which is a smaller version of exactly the
    bias rotation exists to remove. Playing a few more games costs minutes;
    reintroducing the bias costs the result. The caller reports both numbers.
    """
    rotations = max(1, rotations)
    if requested <= 0:
        return [1] * rotations
    whole = -(-requested // rotations)              # ceil
    if cap is not None and whole * rotations > cap:
        whole = max(1, cap // rotations)            # back off to fit the cap
    return [whole] * rotations


def _rotation_meta(requested: int, split: list[int], played: list[int]) -> dict:
    """Per-rotation accounting for the merged result (audit A5, A27).

    Without this a run that lost a rotation to an OOM still reported
    `rotations: 4` and full seat-bias cancellation, with nothing anywhere able
    to notice. `incomplete` is the flag every consumer keys on; the per-rotation
    lists are what make it diagnosable.
    """
    expected = sum(split)
    total = sum(played)
    return {
        "games_requested": requested,
        "games_expected": expected,
        "games_played": total,
        "games_per_rotation_expected": split,
        "games_per_rotation_played": played,
        "rotations_completed": sum(1 for n in played if n > 0),
        "incomplete": total < expected,
    }


def _summarize_by_deck(games: list) -> dict:
    """Aggregate wins by DECK (strip the Ai(n)- seat prefix).

    This is the summarizer the DEFAULT path uses: every rotated run rebuilds
    its merged summary here from scratch, so anything this function forgets is
    absent from production results no matter what the per-rotation summaries
    said. `timeouts` was exactly that (audit A16) — shipped 2026-08-03 into
    forge_log_adapter.summarize(), discarded here, and therefore invisible on
    every rotated run, which is all of them.
    """
    import re as _re
    seat = _re.compile(r"^Ai\(\d+\)-")   # \d+ — a 10-seat pod is still Ai(10)-
    wins: dict = {}
    draws = 0
    timeouts = 0
    for g in games:
        for p in g.get("players") or []:
            wins.setdefault(seat.sub("", p), 0)
    quarantined = 0
    for g in games:
        r = g.get("result") or {}
        if r.get("error") or r.get("missingResult"):
            quarantined += 1     # a crash or a lost record is not a game
            continue
        if r.get("timedOut"):
            timeouts += 1
            # A clock-cut game is a draw, whatever Forge's outcome object says.
            # 83% of 4-pod games were once recorded as wins this way, credited
            # disproportionately to late seats. Counting it here rather than
            # trusting `winner` is what stops a re-parse of a polluted file
            # from re-minting the fake win.
            draws += 1
            continue
        if r.get("draw"):
            draws += 1
        elif r.get("winner"):
            name = seat.sub("", r["winner"])
            wins[name] = wins.get(name, 0) + 1
    total = len(games)
    scored = total - quarantined
    out = {"games": total, "draws": draws, "timeouts": timeouts, "wins": wins,
           "win_rates": {p: round(w / scored, 3) for p, w in wins.items()} if scored else {}}
    if quarantined:
        out["quarantined"] = quarantined
        out["games_scored"] = scored
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--decks", nargs="+", required=True,
                   help=".dck filenames (or deck names known to Forge). 4 decks = 4-player pod.")
    p.add_argument("--deck-dir", default=None, help="Directory containing the .dck files (-D)")
    p.add_argument("--games", type=int, default=10)
    p.add_argument("--format", default="Commander")
    # 300s (the prior default here) was itself an unvalidated guess and
    # turned out to be wrong: a real uncensored calibration batch on the VM
    # (6 games, one fixed 4-deck matchup, no rotation, run at a 900s ceiling
    # so nothing got cut off) measured naturally-concluding games from 81s to
    # 354s (median ~159s) — 300s would have cut off 1 of those 6. 900s is
    # the number we've actually tested against, not another multiplier
    # guess, though this sample is small and one matchup; slower archetypes
    # (stax/mill/politics-heavy, see deck_plan.py TAG_PERSONALITY) weren't
    # represented and could run longer.
    p.add_argument("--clock", type=int, default=900, help="Per-game timeout seconds (draw when exceeded)")
    p.add_argument("--quiet", action="store_true", help="Result-only logs (no per-action events)")
    p.add_argument("--forge-jar", default=None)
    p.add_argument("--agent", choices=["auto", "forge", "shim"], default="auto",
                   help="'auto' (default) = HUMANIZED plan agents via the shim, "
                        "falling back to stock Forge (labeled) if no shim jar. "
                        "'forge' = stock sim CLI. 'shim' = shim with stock AI "
                        "(typed logs + zone ground truth, no plan agents).")
    p.add_argument("--shim-jar", default=None,
                   help="Path to simlab-forge-shim.jar (or set SIMLAB_SHIM_JAR)")
    p.add_argument("--humanize", action="store_true",
                   help="Generate deck plans (deck_plan.py) and run plan agents "
                        "in the shim: human-like mulligans, split attacks, danger "
                        "blocks, threat-gated counterspells. Implies --agent shim. "
                        "Results are 'Sim Lab agent' numbers — label them as such.")
    p.add_argument("--heap", default="4g", help="JVM max heap (default 4g)")
    p.add_argument("--rotate", action="store_true",
                   help="Rotate seat order across sub-runs to cancel Forge's seat bias (recommended for 4-player)")
    p.add_argument("--out", default="./sim_results")
    p.add_argument("--run-id", default=None,
                   help="Job id. Names the raw log forge_raw_<id>.log so the API "
                        "can read the game in progress (GET /sim-live).")
    try:
        run(p.parse_args())
    finally:
        # Covers the sys.exit() paths too: SystemExit unwinds through finally,
        # so a bad decklist does not leave a private profile behind.
        _cleanup_profile()


if __name__ == "__main__":
    main()
