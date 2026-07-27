#!/usr/bin/env python3
"""Is Forge actually shuffling, and how often does a given card show up early?

Forge owns shuffling — we hand it a .dck and it deals the game (CLAUDE.md: don't
reimplement Magic). This script does not fix anything; it checks the claim, so
"deck X keeps opening on Sol Ring" can be answered with a number instead of a
hunch.

Two independent tests:

  1. Opening variety. If a deck were played off a static list, every game with
     that deck would open with the same cards. Counts distinct opening sequences
     per deck across every game it appears in. Anything less than near-100%
     distinct is the signal that something is wrong.

  2. Early-play rate vs the maths. Compares how often a card is actually cast by
     turn N against the hypergeometric odds of having drawn it by then. A rate
     well ABOVE the prediction would mean the deck is front-loaded; at or below
     it means the draw is fair and the card is just an auto-include.

Usage:
    python3 engine/shuffle_check.py                       # every result file
    python3 engine/shuffle_check.py --deck "Kilo Helm"    # one deck's openings
    python3 engine/shuffle_check.py --card "Sol Ring" --card "Arcane Signet"
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
from math import comb
from pathlib import Path

RESULTS = Path(__file__).parent / "sim_results"
_PLAY = re.compile(r"^(.+?) (?:played|cast|activated|triggered) (.+?)(?: \(\d+\))?(?: targeting.*)?$")
_CAST = re.compile(r"^(.+?) (?:cast|activated|triggered) ")
OPENING = 6          # plays compared when testing for a static list
DECK_SIZE = 99       # Commander, commander excluded


def p_drawn(seen: int, copies: int = 1, deck: int = DECK_SIZE) -> float:
    """Hypergeometric: chance at least one copy is among `seen` cards."""
    if seen >= deck:
        return 1.0
    return 1 - comb(deck - copies, seen) / comb(deck, seen)


def load_games(paths: list[str]):
    for f in paths:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a truncated file should not stop the run
            continue
        for i, g in enumerate(d.get("games") or []):
            yield os.path.basename(f), i + 1, g


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--deck", help="Substring of a deck name; default is every deck seen")
    p.add_argument("--card", action="append", default=[],
                   help="Card to rate-check (repeatable). Default: Sol Ring, Arcane Signet")
    p.add_argument("--results", default=str(RESULTS))
    a = p.parse_args()
    cards = a.card or ["Sol Ring", "Arcane Signet"]

    paths = sorted(glob.glob(os.path.join(a.results, "sim_*.json")))
    if not paths:
        print(f"no result files in {a.results} — run a simulation first")
        return 1

    openings: dict[str, list[tuple]] = collections.defaultdict(list)
    seen_by_turn: collections.Counter = collections.Counter()
    deckgames = 0
    games = 0
    games_with: collections.Counter = collections.Counter()

    for _f, _n, g in load_games(paths):
        players = g.get("players") or []
        if not players:
            continue
        games += 1
        deckgames += len(players)
        first: dict[str, list[str]] = collections.defaultdict(list)
        cast_by: dict[str, set] = {c: set() for c in cards}

        for t in g.get("turns") or []:
            tn = t.get("turn", 99)
            for e in t.get("events") or []:
                raw = e.get("raw", "")
                if e.get("action") in ("land_drop", "stack_add"):
                    m = _PLAY.match(raw)
                    if m and len(first[m.group(1)]) < OPENING:
                        first[m.group(1)].append(m.group(2))
                if e.get("action") == "stack_add":
                    obj = e.get("object") or ""
                    for c in cards:
                        if obj.startswith(c):
                            m = _CAST.match(raw)
                            who = m.group(1) if m else None
                            if who and who not in cast_by[c]:
                                cast_by[c].add(who)
                                for bucket in (3, 5, 10, 99):
                                    if tn <= bucket:
                                        seen_by_turn[(c, bucket)] += 1
        for who, seq in first.items():
            openings[who].append(tuple(seq))
        for c in cards:
            if cast_by[c]:
                games_with[c] += 1

    print(f"{games} games, {deckgames} deck-games, from {len(paths)} result files\n")

    print("1. Opening variety — a static list would repeat itself")
    rows = []
    for who, seqs in openings.items():
        name = re.sub(r"^Ai\(\d+\)-", "", who)
        if a.deck and a.deck.lower() not in name.lower():
            continue
        rows.append((name, len(seqs), len(set(seqs))))
    agg: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for name, n, u in rows:
        agg[name][0] += n
        agg[name][1] += u
    worst = 1.0
    for name, (n, u) in sorted(agg.items(), key=lambda kv: -kv[1][0])[:12]:
        share = u / n if n else 1.0
        worst = min(worst, share) if n >= 10 else worst
        flag = "" if share > 0.9 or n < 10 else "   <-- SUSPICIOUS"
        print(f"   {name[:30]:30} {u:4}/{n:<4} distinct openings  {share:6.0%}{flag}")
    print(f"\n   {'PASS' if worst > 0.9 else 'FAIL'}: lowest distinct-opening share "
          f"among decks with 10+ games is {worst:.0%}. Forge is "
          f"{'shuffling' if worst > 0.9 else 'NOT shuffling — investigate'}.\n")

    print("2. Early-play rate vs hypergeometric expectation (per deck-game)")
    print(f"   {'card':18} {'by T3':>7} {'pred':>7} {'by T5':>7} {'pred':>7} {'ever':>7}")
    for c in cards:
        o3 = seen_by_turn[(c, 3)] / deckgames if deckgames else 0
        o5 = seen_by_turn[(c, 5)] / deckgames if deckgames else 0
        ev = seen_by_turn[(c, 99)] / deckgames if deckgames else 0
        # ~7 opening cards plus a draw a turn.
        print(f"   {c[:18]:18} {o3:6.1%} {p_drawn(10):6.1%} {o5:6.1%} {p_drawn(12):6.1%} {ev:6.1%}")
    print("\n   Above prediction would mean the deck is front-loaded. At or below it,")
    print("   the draw is fair and the card is simply in every list.\n")

    print("3. Why it FEELS frequent — the pod multiplies it")
    for c in cards:
        print(f"   {c[:18]:18} appears in {games_with[c] / games:5.0%} of games "
              f"(any player)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
