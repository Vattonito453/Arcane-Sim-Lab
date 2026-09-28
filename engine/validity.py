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

`commander_missing` (certain, any path): Forge played a seat without its
commander, because it refused to load it at startup or the deck file lists no
commander in a Commander run (run_sim writes `meta.commander_fidelity`; a
refused card is also in `meta.unsupported_cards`). Both Ral decks lost "Ral,
Monsoon Mage // Ral, Leyline Prodigy" this way for 30 games. The run did not
test the deck as built, so it is polluted.

`commander_never_cast` (a note, shim path only): the commander loaded, but it
never appears in any zone record over the run. The shim records a commander
when it leaves the command zone, so this means Forge's AI never cast it: a
commander scripted AI:RemoveDeck:All, such as Winter, Cynical Opportunist, or
in a short run just chance. That is a limit of Forge's AI, not a defect in
the run, so it does not change the quality (owner decision 2026-09-27: only a
commander that FAILED TO LOAD makes a run polluted). It is still a flag with
a reason, so every surface that shows reasons shows it.

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
    "incomplete_run": POLLUTED,
    "commander_missing": POLLUTED,
    "suspected_clock_cut_wins": SUSPECT,
    "mixed_pilot": SUSPECT,
    "unknown_pilot": SUSPECT,
    # A note: shown with its reason, never lowers the quality.
    "commander_never_cast": CLEAN,
}

# Bumped when the RULES here change, so a cached verdict computed by an older
# version is recomputed rather than trusted. Coaching stamps this beside its
# own cache and regenerates on a mismatch. The analysis cache does not key on
# it: mtg_engine._read_analysis replaces the cached report's verdict with the
# one just computed for the result, so every read carries the current rules.
# The result endpoints never cache a verdict at all (_read_result).
# 2 (2026-09-26): commander_missing.
# 3 (2026-09-27): commander_missing only for a commander Forge refused or a
#   deck file without one; a loaded commander never cast is the
#   commander_never_cast note.
# 4 (2026-09-28): mixed_pilot only when some rotations ran the plan agent and
#   some did not; an all-stock run is no longer called a mixed pod.
VALIDITY_VERSION = 4


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
    elif meta.get("incomplete"):
        # A rotation that did not finish leaves the seats unevenly covered,
        # which is the same defect rotation exists to remove, in a smaller
        # dose. The games themselves are real and worth keeping; what they
        # cannot do is rank decks against each other.
        done = meta.get("rotations_completed")
        total = meta.get("rotations")
        played = meta.get("games_played")
        expected = meta.get("games_expected")
        detail = (f"{done} of {total} seat rotations finished"
                  if done is not None and total else "it did not finish")
        if played and expected:
            detail += f", {played} of {expected} games played"
        flags.append("incomplete_run")
        reasons.append(
            f"The run was cut short ({detail}), so the decks did not each sit "
            f"in every seat the same number of times. The games that ran are "
            f"real; the comparison between decks is not.")

    by_rotation = meta.get("humanized_by_rotation")
    # Mixed means SOME rotations ran the plan agent and some did not. An
    # all-stock run (every entry false: a stock-Forge arm run through the
    # shim) is a clean stock experiment, and "Mixed pod: 0 of 4 rotations ran
    # the plan agent" was simply untrue (repair plan WS11 task 10).
    if (isinstance(by_rotation, list) and by_rotation and any(by_rotation)
            and not all(by_rotation)):
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

    missing, never_cast = _commander_findings(meta)
    if missing:
        flags.append("commander_missing")
        reasons.append(_missing_reason(missing))
    if never_cast:
        flags.append("commander_never_cast")
        reasons.append(_never_cast_reason(never_cast))

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


# ---------------------------------------------------------------------------
# Pilot disclosure (repair plan WS11 task 10)
# ---------------------------------------------------------------------------

_SHIM_PREFIX = "simlab-forge-shim"
# Plan version 2 carries these tutoring-hotfix flags (engine/deck_plan.py
# V2_FIX). Named here only to count them; the UI never shows the flag names.
_PLAN_FIX_COUNT = 4


def _deck_agents(meta: dict) -> dict[str, set]:
    """{deck: {"plan", "stock", ...}} from the per-rotation seat records (or
    the one-rotation meta.agents aligned with meta.players)."""
    out: dict[str, set] = {}
    for rot in meta.get("rotations_detail") or []:
        if not isinstance(rot, dict):
            continue
        seats, agents = rot.get("seats") or [], rot.get("agents") or []
        for deck, agent in zip(seats, agents):
            out.setdefault(str(deck), set()).add(str(agent))
    if not out and isinstance(meta.get("agents"), list):
        players = meta.get("players") or [f"seat {i + 1}" for i in range(len(meta["agents"]))]
        for deck, agent in zip(players, meta["agents"]):
            out.setdefault(str(deck), set()).add(str(agent))
    return out


def pilot(meta: dict) -> dict:
    """Who piloted a run, disclosed on every run page.

    {"kind", "agent", "shim", "plan_decks", "stock_decks", "plan_version",
     "plan_fix", "random", "label", "note"}; plan_decks / stock_decks count
    the decks on each pilot (None when the run records no per-seat pilot):
      kind         "plan" (every seat on Sim Lab's plan agent), "stock"
                   (Forge's own AI; on the stdout path or through the shim),
                   "mixed", or "unknown" (written before runs recorded it)
      agent        meta.agent verbatim ("simlab-forge-shim/0.15.0")
      shim         the shim version, or None (stock stdout path, or a
                   rotated run whose rotations disagreed)
      plan_version, plan_fix   from meta when run_sim recorded them (from
                   2026-09-28); plan_fix is the list of flags that were on
      random       True while any random dial remains in the pilot: every
                   plan seat to date skips some blocks at random by design
                   (owner decision 8 retires that at E8). A run that records
                   meta.random_dials is taken at its word.
      label, note  the words the UI shows. "Humanized" is no longer a
                   product claim (owner decision 8); the note says what is
                   true instead: "Some choices are random on purpose."
    Copy rules apply (these strings reach the UI): no em dash."""
    meta = meta or {}
    agent = meta.get("agent") if isinstance(meta.get("agent"), str) else None
    shim = None
    if agent and agent.startswith(_SHIM_PREFIX + "/"):
        shim = agent.split("/", 1)[1] or None
    via_shim = bool(agent and agent.startswith(_SHIM_PREFIX))
    per_deck = _deck_agents(meta)
    plan_decks = sorted(d for d, a in per_deck.items() if a == {"plan"})
    stock_decks = sorted(d for d, a in per_deck.items() if a and "plan" not in a)
    by_rot = meta.get("humanized_by_rotation")
    humanized = meta.get("humanized")
    if per_deck:
        if len(plan_decks) == len(per_deck):
            kind = "plan"
        elif len(stock_decks) == len(per_deck):
            kind = "stock"
        else:
            kind = "mixed"
    elif humanized is True:
        kind = "plan"
    elif isinstance(by_rot, list) and any(by_rot):
        kind = "mixed"
    elif humanized is False:
        kind = "stock"
    else:
        kind = "unknown"

    plan_version = meta.get("plan_version")
    plan_version = plan_version if isinstance(plan_version, int) else None
    fix = meta.get("plan_fix")
    plan_fix = [str(f) for f in fix] if isinstance(fix, list) else None

    random_dials = meta.get("random_dials")
    random = (random_dials if isinstance(random_dials, bool)
              else kind in ("plan", "mixed"))

    shim_words = f"shim {shim}" if shim else ("Sim Lab's shim" if via_shim else None)
    plan_words = []
    if plan_version is not None:
        plan_words.append(f"plan version {plan_version}")
    if plan_fix is not None and plan_version is not None and plan_version >= 2:
        on = len(plan_fix)
        plan_words.append("tutoring fixes on" if on >= _PLAN_FIX_COUNT
                          else "tutoring fixes off" if on == 0
                          else f"{on} of {_PLAN_FIX_COUNT} tutoring fixes on")
    detail = ", ".join(w for w in [*plan_words, shim_words] if w)
    tail = f" ({detail})" if detail else ""
    if kind == "plan":
        label = f"Piloted by Sim Lab's plan agent on Forge's AI{tail}."
    elif kind == "stock":
        label = (f"Piloted by Forge's own AI{tail}." if via_shim
                 else "Piloted by Forge's own AI.")
    elif kind == "mixed":
        n_plan, n_stock = len(plan_decks), len(stock_decks)
        if per_deck:
            label = (f"Mixed pilots: {n_plan} {'deck' if n_plan == 1 else 'decks'} on "
                     f"Sim Lab's plan agent, the rest on Forge's own AI{tail}.")
        else:
            label = (f"Mixed pilots: some seat rotations ran Sim Lab's plan agent "
                     f"and the rest Forge's own AI{tail}.")
    else:
        label = "Pilot not recorded: this run predates it."
    return {
        "kind": kind,
        "agent": agent,
        "shim": shim,
        "plan_decks": len(plan_decks) if per_deck else None,
        "stock_decks": len(stock_decks) if per_deck else None,
        "plan_version": plan_version,
        "plan_fix": plan_fix,
        "random": bool(random),
        "label": label,
        "note": "Some choices are random on purpose." if random else None,
    }


def _commander_findings(meta: dict) -> tuple[list[tuple], list[tuple]]:
    """(missing, never_cast) from meta.commander_fidelity.

    missing     [(player, refused names, or None for a deck file with no
                commander)]: Forge played the seat without its commander.
    never_cast  [(player, names, games)]: loaded, never in a zone record.

    Rows written on 2026-09-26 (validity 2) carry only `missing`, which lumps
    both cases together; they are split here the way run_sim now splits them,
    by whether Forge's refusal list (meta.unsupported_cards) names the
    commander exactly as the deck spelled it. Files older than that carry no
    rows and trip neither."""
    unsupported = {n.casefold() for n in _name_list(meta.get("unsupported_cards"))}
    missing: list[tuple] = []
    never_cast: list[tuple] = []
    rows = meta.get("commander_fidelity")
    for f in rows if isinstance(rows, list) else []:
        if not isinstance(f, dict):
            continue
        player = str(f.get("player") or f.get("deck") or "a deck")
        if f.get("no_commander"):
            missing.append((player, None))
            continue
        was_missing = _name_list(f.get("missing"))
        refused = f.get("refused")
        refused = ([c for c in was_missing if c.casefold() in unsupported]
                   if refused is None else _name_list(refused))
        never = f.get("never_cast")
        never = ([c for c in was_missing if c not in refused]
                 if never is None else _name_list(never))
        games = _count(f.get("games"))
        if refused:
            missing.append((player, refused))
        if never and games > 0:
            never_cast.append((player, never, games))
    return missing, never_cast


def _name_list(value) -> list[str]:
    """A list of names from a field that should be one. A lone string is one
    name, never a list of its characters; anything else malformed is empty."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    return []


def _count(value) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _names(names: list[str]) -> str:
    # Card names contain commas, so several are separated by semicolons.
    return "; ".join(names)


def _missing_reason(missing: list[tuple]) -> str:
    """Plain words for the UI: no em dash (CLAUDE.md copy rule)."""
    parts = []
    for player, refused in missing:
        if refused is None:
            parts.append(f"{player}'s deck file lists no commander, so Forge played "
                         f"that deck without one.")
        else:
            one = len(refused) == 1
            parts.append(f"Forge refused to load {player}'s "
                         f"{'commander' if one else 'commanders'} ({_names(refused)}) and "
                         f"played that deck without {'it' if one else 'them'}.")
    deck = "deck" if len(missing) == 1 else "decks"
    return " ".join(parts) + f" These results do not describe the {deck} as built."


def _never_cast_reason(never_cast: list[tuple]) -> str:
    """The note for a commander that loaded and was never cast. It reports a
    limit of Forge's AI, so it says what the run shows without condemning it."""
    games = max(g for _, _, g in never_cast)
    where = "in the one game played" if games == 1 else f"in any of the {games} games"
    if len(never_cast) == 1:
        player, names, _ = never_cast[0]
        one = len(names) == 1
        cmd = "commander" if one else "commanders"
        # "that commander", not "its commander": with partners, the other one
        # may well have been cast.
        return (f"{player}'s {cmd} ({_names(names)}) loaded, but Forge's AI never cast "
                f"{'it' if one else 'them'} {where}, so the deck was tested without "
                f"{'that commander' if one else 'those commanders'} in play. Over a full "
                f"run that usually means Forge's AI doesn't "
                f"cast {'that card' if one else 'those cards'} on its own.")
    items = "; ".join(f"{p} ({_names(n)})" for p, n, _ in never_cast)
    return (f"These commanders loaded, but Forge's AI never cast them {where}: {items}. "
            f"Those decks were tested without those commanders in play. Over a full run "
            f"that usually means Forge's AI doesn't cast those cards on its own.")


def summarize_flags(verdict: dict) -> str:
    """One short line for a log or a CLI, never for the UI."""
    if not verdict["flags"]:
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
