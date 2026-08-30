#!/usr/bin/env python3
"""Scorecard aggregation: units, censoring, and absent-is-not-zero.

Run: python3 engine/tests/test_scorecard.py   ->  ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scorecard import bare, scorecards, true_round  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sim_sample.json"


def _game(turn_players, result, rubric=None, events_by_turn=None):
    turns = []
    for i, p in enumerate(turn_players):
        turns.append({
            "turn": i + 1,
            "active_player": p,
            "events": (events_by_turn or {}).get(i, []),
        })
    return {
        "players": sorted({p for p in turn_players}),
        "turns": turns,
        "result": result,
        "rubric": rubric or [],
    }


def test_bare():
    assert bare("Ai(2)-Kilo Helm Final") == "Kilo Helm Final"
    assert bare("Kilo Helm Final") == "Kilo Helm Final"
    assert bare("") == ""


def test_true_round_counts_per_player():
    # Four seats, two full rounds: every player took 2 turns -> round 2.
    g = _game(["A", "B", "C", "D", "A", "B", "C", "D"], {"draw": True})
    assert true_round(g) == 2, true_round(g)

    # After D is eliminated a round is THREE turns. Dividing 11 turns by a
    # constant 4 seats gives 2 (wrong); counting per player gives A's 4th
    # turn = round 4.
    g2 = _game(["A", "B", "C", "D",
                "A", "B", "C",
                "A", "B", "C",
                "A"], {"draw": True})
    assert true_round(g2) == 4, true_round(g2)


def test_censored_games_excluded_from_win_rate_but_counted():
    decided = _game(["A", "B"], {"winner": "Ai(1)-A", "draw": False,
                                 "seats": [{"name": "Ai(1)-A", "alive": True},
                                           {"name": "Ai(2)-B", "alive": False}]})
    killed = _game(["A", "B"], {"winner": None, "draw": True, "timedOut": True,
                                "seats": []})
    sc = scorecards({"games": [decided, killed]})
    by = {d["deck"]: d for d in sc["decks"]}
    a = by["A"]
    assert a["games"] == 2, a["games"]
    assert a["censored"] == 1, a["censored"]
    # 1 win over 1 decided game, NOT over 2 played.
    assert a["winRate"] == 1.0, a["winRate"]
    assert sc["run"]["censored"] == 1
    assert sc["run"]["decided"] == 1


def test_absent_behaviour_is_none_not_zero():
    """A pre-0.9.0 run has no rubric records. Sections must be None so the UI
    can say "not recorded" instead of drawing a zero."""
    g = _game(["A", "B"], {"winner": "Ai(1)-A", "draw": False, "seats": []})
    sc = scorecards({"games": [g]})
    a = [d for d in sc["decks"] if d["deck"] == "A"][0]
    assert a["blocking"] is None
    assert a["attacking"] is None
    assert a["mulligans"] is None
    assert sc["run"]["hasBehaviour"] is False


def test_rubric_aggregation_math():
    rubric = [
        {"kind": "block", "player": "Ai(1)-A", "incoming": 4, "blocked": 1,
         "legalMissed": 3, "freeTaken": 1, "freeMissed": 1,
         "v3": 1, "v2": 0, "v1": 0, "v0": 1, "lifeTaken": 6},
        {"kind": "block", "player": "Ai(1)-A", "incoming": 6, "blocked": 1,
         "legalMissed": 1, "freeTaken": 0, "freeMissed": 0,
         "v3": 0, "v2": 1, "v1": 0, "v0": 0, "lifeTaken": 4},
        {"kind": "attack", "player": "Ai(1)-A", "attackers": 3,
         "heldEligible": 1, "defenders": 2, "heldBestTough": 5,
         "backBiggest": 3},
        {"kind": "mull", "player": "Ai(1)-A", "mulls": 0, "lands": 3},
        {"kind": "mull", "player": "Ai(1)-A", "mulls": 2, "lands": 4},
    ]
    g = _game(["A", "B"], {"winner": "Ai(1)-A", "draw": False, "seats": []},
              rubric=rubric)
    sc = scorecards({"games": [g]})
    a = [d for d in sc["decks"] if d["deck"] == "A"][0]

    b = a["blocking"]
    assert b["combats"] == 2
    assert b["faced"] == 10
    assert b["engage"] == 2 / 10, b["engage"]
    # declined is over BLOCKABLE attackers (blocked + legalMissed), never all
    # incoming: an attacker nothing could legally block is not a decision.
    assert b["declined"] == 4 / 6, b["declined"]
    assert b["freeCapture"] == 1 / 2, b["freeCapture"]
    assert b["chumpShare"] == 1 / 3, b["chumpShare"]
    assert b["damagePerCombat"] == 5.0, b["damagePerCombat"]

    at = a["attacking"]
    # Eligible denominator: 3 attacked of 4 that could have.
    assert at["commitment"] == 3 / 4, at["commitment"]
    assert at["defendersPerAttack"] == 2.0
    assert at["keptEnough"] == 1.0

    m = a["mulligans"]
    assert m["seatGames"] == 2
    assert m["kept7"] == 0.5, m["kept7"]
    assert m["mullsPerGame"] == 1.0, m["mullsPerGame"]
    assert m["landsKept"] == 3.5, m["landsKept"]
    assert sc["run"]["hasBehaviour"] is True


def test_death_round_from_loss_lines():
    events = {6: [{"action": "game_outcome",
                   "raw": "Ai(2)-B has lost because life total reached 0"}]}
    g = _game(["A", "B", "A", "B", "A", "B", "A"],
              {"winner": "Ai(1)-A", "draw": False, "seats": []},
              events_by_turn=events)
    sc = scorecards({"games": [g]})
    by = {d["deck"]: d for d in sc["decks"]}
    # The loss line sits on index 6 (A's 4th turn) -> round 4.
    assert by["B"]["medianDeathRound"] == 4, by["B"]["medianDeathRound"]
    assert by["A"]["medianDeathRound"] is None


def test_real_fixture_end_to_end():
    """The committed 2-game fixture predates the rubric stream, so it proves
    the outcome half works while the behaviour half stays absent."""
    result = json.loads(FIXTURE.read_text(encoding="utf-8"))
    sc = scorecards(result)
    assert len(sc["decks"]) == 4, [d["deck"] for d in sc["decks"]]
    assert sc["run"]["games"] == 2
    assert sc["run"]["baseline"] == 0.25
    assert sc["run"]["hasBehaviour"] is False
    total_wins = sum(d["wins"] for d in sc["decks"])
    assert total_wins <= 2, total_wins
    for d in sc["decks"]:
        assert d["games"] == 2, (d["deck"], d["games"])
        if d["wins"]:
            assert d["medianWinRound"] and d["medianWinRound"] > 0
    # Sorted best-first so the UI never has to.
    rates = [d["winRate"] or 0 for d in sc["decks"]]
    assert rates == sorted(rates, reverse=True), rates


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
