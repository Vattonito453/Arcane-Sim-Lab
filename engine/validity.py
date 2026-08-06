#!/usr/bin/env python3
"""One place that decides whether a sim result can be trusted, and how far.

## Why this exists (audit A25)

Every consumer of a result file — the home leaderboard, the home tallies,
analysis.py, deck_telemetry.py, the coach — read whatever was on disk with no
validity check at all. That was survivable while the pipeline was believed
correct. It stopped being survivable on 2026-08-03, when a manual raw-log audit
found that 83% of 4-player games had been force-drawn by the clock and recorded
as WINS, credited disproportionately to late seats. Those files are still in
`sim_results/`, they still look exactly like good ones, and until this module
existed nothing downstream could tell the difference.

## What it does NOT do

It does not repair anything and it does not hide anything. It returns a verdict
plus the reasons behind it, so a caller can decide: the coach refuses polluted
input, the leaderboard labels it, the index carries it. Silently dropping runs
would leave someone staring at a deck whose history had gone missing.

## The signals, and how sure each one is

`clock_cut_wins` (certain, when the file says so): a game marked `timedOut`
that still carries a winner. The clock cut it off; the winner is an artifact.

`suspected_clock_cut_wins` (inferred): the same thing in a file written before
the shim stamped `timedOut`. The verified signature from the audit is
`duration_ms >= clock * 1000`, but `meta.clock` was not recorded before
2026-08-06, so for older files this checks the clock values the pipeline
actually used (`_HISTORICAL_CLOCKS`) and requires the overshoot to be small —
Forge reports these as e.g. "ended in 240002 ms", landing milliseconds past the
wall, whereas a natural game lands nowhere near it. Inferred, so it downgrades
a run to `suspect` rather than condemning it.

`not_rotated`: a single-seat run. Forge's seat bias is large (measured: seat 1
wins ~11%, seat 4 ~36%), so these win rates are not comparable to anything.

`mixed_pilot`: some seats ran the plan agent and some fell back to stock
(audit A8). A mixed pod is a different experiment, not a degraded one.

`unknown_pilot`: written before the shim recorded which agent ran.

CLI:
    python3 engine/validity.py <result.json> [more.json ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Every per-game clock the pipeline has shipped with, newest first: 900 s
# (2026-08-03, measured), 300 s (2026-08-03, a guess that was too short), 240 s
# and 120 s (the original defaults). Only used for files whose meta predates
# `clock` being recorded.
_HISTORICAL_CLOCKS = (900, 300, 240, 120)

# How far past the wall a clock-cut game may land before we stop believing the
# clock explains it. Forge writes the result the moment the timeout fires, so
# the real overshoot is milliseconds; 30 s is generous by three orders of
# magnitude and still nowhere near a natural game at the next clock up.
_OVERSHOOT_MS = 30_000

CLEAN = "clean"
SUSPECT = "suspect"
POLLUTED = "polluted"

_RANK = {CLEAN: 0, SUSPECT: 1, POLLUTED: 2}

# How bad each signal is on its own. "polluted" means the file demonstrably
# contains results that are artifacts; "suspect" means it cannot be placed.
_SEVERITY = {
    "clock_cut_wins": POLLUTED,
    "not_rotated": POLLUTED,
    "suspected_clock_cut_wins": SUSPECT,
    "mixed_pilot": SUSPECT,
    "unknown_pilot": SUSPECT,
}

# Bumped when the RULES here change, so a cached verdict computed by an older
# version is recomputed rather than trusted. Consumers that cache a derived
# report (analysis, coaching) stamp this alongside their own version.
VALIDITY_VERSION = 1


def _clock_seconds(meta: dict) -> int | None:
    c = meta.get("clock")
    return int(c) if isinstance(c, (int, float)) and c > 0 else None


def assess(result: dict) -> dict:
    """Verdict for one loaded result file. Never raises on a malformed file."""
    meta = result.get("meta") or {}
    games = result.get("games") or []
    flags: list[str] = []
    reasons: list[str] = []

    clock = _clock_seconds(meta)
    clock_cut_wins = 0
    suspected = 0
    timed_out = 0

    for g in games:
        r = (g or {}).get("result") or {}
        dur = r.get("duration_ms")
        has_winner = bool(r.get("winner")) and not r.get("draw")
        if r.get("timedOut"):
            timed_out += 1
            if has_winner:
                clock_cut_wins += 1
            continue
        if not has_winner or not isinstance(dur, (int, float)):
            continue
        if clock is not None:
            if dur >= clock * 1000:
                clock_cut_wins += 1
        else:
            for t in _HISTORICAL_CLOCKS:
                wall = t * 1000
                if wall <= dur <= wall + _OVERSHOOT_MS:
                    suspected += 1
                    break

    if clock_cut_wins:
        flags.append("clock_cut_wins")
        reasons.append(
            f"{clock_cut_wins} of {len(games)} games were cut off by the clock "
            f"and still recorded a winner. Those wins are artifacts of the "
            f"timeout, not results.")
    elif suspected:
        flags.append("suspected_clock_cut_wins")
        reasons.append(
            f"{suspected} of {len(games)} games ended within {_OVERSHOOT_MS // 1000} s "
            f"of a per-game clock this pipeline has used, and recorded a winner. "
            f"This run predates the clock being recorded, so it cannot be "
            f"confirmed either way.")

    if meta.get("source") != "rotated":
        flags.append("not_rotated")
        reasons.append(
            "Not seat-rotated. Forge's seat bias is large (seat 1 wins ~11%, "
            "seat 4 ~36%), so these win rates measure seating as much as decks.")

    by_rotation = meta.get("humanized_by_rotation")
    if isinstance(by_rotation, list) and by_rotation and not all(by_rotation):
        flags.append("mixed_pilot")
        reasons.append(
            f"Mixed pod: {sum(1 for x in by_rotation if x)} of {len(by_rotation)} "
            f"rotations ran the plan agent and the rest fell back to stock. "
            f"That is a different experiment, not a degraded one.")
    elif "humanized" not in meta:
        flags.append("unknown_pilot")
        reasons.append(
            "Written before the run recorded which agent piloted it, so it "
            "cannot be compared against either stock or agent baselines.")

    # Severity is the worst flag present, never the last one evaluated. An
    # earlier version let a "suspect" flag mask a later "polluted" one purely
    # by evaluation order, which understates exactly the runs that matter most.
    quality = CLEAN
    for f in flags:
        s = _SEVERITY.get(f, SUSPECT)
        if _RANK[s] > _RANK[quality]:
            quality = s

    return {
        "version": VALIDITY_VERSION,
        "quality": quality,
        "usable_for_ranking": quality == CLEAN,
        "flags": flags,
        "reasons": reasons,
        "games": len(games),
        "timed_out": timed_out,
        "clock_cut_wins": clock_cut_wins,
        "suspected_clock_cut_wins": suspected,
        "clock": clock,
        "source": meta.get("source"),
        "humanized": meta.get("humanized"),
        "agent": meta.get("agent"),
    }


def summarize_flags(verdict: dict) -> str:
    """One short line for a log or a CLI, never for the UI."""
    if verdict["quality"] == CLEAN:
        return "clean"
    return f"{verdict['quality']}: {', '.join(verdict['flags'])}"


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for arg in sys.argv[1:]:
        p = Path(arg)
        try:
            v = assess(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001 — a bad file is a finding, not a crash
            print(f"{p.name}: unreadable: {e}")
            continue
        print(f"{p.name}: {summarize_flags(v)}")
        for r in v["reasons"]:
            print(f"    - {r}")


if __name__ == "__main__":
    main()
