#!/usr/bin/env python3
"""Win rates, published once: decided games are the one denominator.

Why (repair plan WS11 task 9, UX review problem 10): the run page divided a
deck's wins by every game played, the scorecards divided by the games the
clock did not cut off, the prediction table printed a third figure from
summary.win_rates, and the results index crowned whichever deck topped that
map "Winner" even at exactly an even share. Kess read "50%", "4 of 7, 57%"
and "Simulated 50.0%" on one page. Every surface now reads this module's
output and formats nothing but the digits it is told to.

The rules, in one place:

  decided     a game that finished with a winner. Not decided: a game the
              per-game clock or the turn cap stopped (a clock-cut game is a
              draw whatever winner the record carries, audit A16), a draw
              Forge declared, and a crash or lost record. This is the
              definition the prediction model's training arm used ("stock
              Forge, decided games": not timedOut and a winner) and the one
              the R1 rank check read, so the figure a page shows and the
              figure the model was fitted against are the same quantity.
  rate        wins over the decided games the deck sat in.
  digits      whole percents below WHOLE_PERCENT_BELOW decided games, one
              decimal from there. An eight-game run cannot carry "57.1%".
  average     an even share of the pod (1/N): the only reference a win rate
              is shown against until the archetype baselines are re-measured
              under the plan agent (decision 13).
  leader      "leader" when one deck has the most wins and is above the
              average; "tie" when several share the most wins above it; "none"
              ("no clear leader") when no deck beats an even share or nothing
              was decided.

Stdlib only; no card knowledge.
"""
from __future__ import annotations

import re
from collections import Counter

VERSION = 1
WHOLE_PERCENT_BELOW = 30

_AI = re.compile(r"^Ai\(\d+\)-")
_WON_RAW = re.compile(r"([^.]+?) has won")
UNDECIDED = ("clock", "turn_cap", "draw", "no_result")


def bare(player: str) -> str:
    """"Ai(2)-Kess, Reanimator" -> "Kess, Reanimator"."""
    return _AI.sub("", str(player or "")).strip()


def _winner(r: dict) -> str | None:
    """The winner a result names: result.winner, else the "X has won" line a
    rare old record carries with a null winner (the run page's games table
    reads the same fallback, so the table and the rate cannot disagree)."""
    w = r.get("winner")
    if w:
        return str(w)
    m = _WON_RAW.search(str(r.get("raw") or ""))
    return m.group(1).strip() if m else None


def outcome(game: dict) -> str:
    """How one game ended, for the denominator: "won", or one of UNDECIDED."""
    r = (game or {}).get("result") or {}
    if r.get("error") or r.get("missingResult"):
        return "no_result"
    if r.get("timedOut"):
        return "clock"
    if r.get("turnCapped"):
        return "turn_cap"
    if r.get("draw"):
        return "draw"
    return "won" if _winner(r) else "no_result"


def winner_of(game: dict) -> str | None:
    """The bare winner of a decided game, None for any other."""
    if outcome(game) != "won":
        return None
    return bare(_winner((game or {}).get("result") or {}))


def _publish(roster: list[str], wins: dict, decided: dict, played: dict,
             n_games: int, n_decided: int, undecided: dict) -> dict:
    pod = len(roster)
    average = (1 / pod) if pod else None
    decks = []
    for name in roster:
        d = decided.get(name, 0)
        w = wins.get(name, 0)
        decks.append({"deck": name, "wins": w, "decided": d,
                      "games": played.get(name, 0),
                      "rate": round(w / d, 4) if d else None})
    decks.sort(key=lambda x: (-(x["rate"] if x["rate"] is not None else -1.0),
                              -x["wins"], x["deck"].casefold()))
    leader = {"kind": "none", "decks": [], "rate": None}
    top = decks[0] if decks else None
    if top and top["rate"] is not None and top["wins"] > 0:
        tops = [x["deck"] for x in decks
                if x["wins"] == top["wins"] and x["rate"] == top["rate"]]
        # "At or below 1/N" is no clear leader (UX review 5.2 item 6): a deck
        # at exactly an even share of a 4-deck pod did what chance does.
        if average is None or top["rate"] > average + 1e-9:
            leader = {"kind": "tie" if len(tops) > 1 else "leader",
                      "decks": tops, "rate": top["rate"]}
    return {
        "version": VERSION,
        "games": n_games,
        "decided": n_decided,
        "undecided": {k: int(undecided.get(k, 0)) for k in UNDECIDED},
        "pod": pod,
        "average": average,
        "digits": 0 if n_decided < WHOLE_PERCENT_BELOW else 1,
        "decks": decks,
        "leader": leader,
    }


def standings(result: dict) -> dict:
    """The published win rates for one result file (see module docstring).

    The roster comes from the games' players, not from the summary, so a
    winless deck is listed and a 4-deck pod is never sized as a 1-deck pod."""
    roster: list[str] = []
    seen: set[str] = set()
    wins: Counter = Counter()
    decided: Counter = Counter()
    played: Counter = Counter()
    counts: Counter = Counter()
    games = (result or {}).get("games") or []

    def add(name: str) -> None:
        if name and name not in seen:
            seen.add(name)
            roster.append(name)

    for g in games:
        players = [bare(p) for p in (g or {}).get("players") or []]
        if not players:
            # A record with no seat list still names its seats in the
            # result's per-seat survival rows.
            seats = ((g or {}).get("result") or {}).get("seats") or []
            players = [bare(s.get("name")) for s in seats
                       if isinstance(s, dict) and s.get("name")]
        for p in players:
            add(p)
            played[p] += 1
        how = outcome(g)
        counts[how] += 1
        if how != "won":
            continue
        for p in players:
            decided[p] += 1
        w = winner_of(g)
        if w not in players:          # a winner outside the seat list: still counted
            add(w)
            decided[w] += 1
        wins[w] += 1
    return _publish(roster, wins, decided, played, len(games), counts["won"],
                    {k: counts[k] for k in UNDECIDED})


def from_summary(summary: dict) -> dict:
    """The same publication from a run summary alone (a job's status, which
    carries no games). Every decided game has exactly one winner and the
    summarizers count a win only for such a game (clock-cut, drawn and
    crashed games are never credited, audit A16), so the decided count is
    the sum of the wins and every deck in the pod sat in each of them. A
    summary cannot tell a turn-capped game from a draw, so both count as
    "draw" here; standings() on the games tells them apart."""
    s = summary or {}
    wins: Counter = Counter()
    roster: list[str] = []
    for key, w in (s.get("wins") or {}).items():
        name = bare(key)
        if name not in roster:
            roster.append(name)
        try:
            wins[name] += int(w or 0)
        except (TypeError, ValueError):
            continue
    n_decided = sum(wins.values())
    n_games = int(s.get("games") or 0)
    timeouts = int(s.get("timeouts") or 0)
    quarantined = int(s.get("quarantined") or 0)
    draws = max(n_games - n_decided - timeouts - quarantined, 0)
    decided = {name: n_decided for name in roster}
    played = {name: n_games for name in roster}
    return _publish(roster, wins, decided, played, n_games, n_decided,
                    {"clock": timeouts, "draw": draws, "no_result": quarantined})


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    for arg in sys.argv[1:]:
        data = json.loads(Path(arg).read_text(encoding="utf-8"))
        print(arg, json.dumps(standings(data), indent=1))
