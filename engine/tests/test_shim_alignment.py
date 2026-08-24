#!/usr/bin/env python3
"""Shim JSONL alignment and quarantine (audit A6, A4).

A6, repro'd by the audit: parse_shim_jsonl rebuilt a stdout-shaped log and
then attached zones, agent telemetry and timedOut POSITIONALLY. The rebuild
only emitted a "Game Result" line for games that had a result record, so a
single lost record (a truncated JSONL line, an OOM-kill mid-flush) merged two
games into one parsed game and shifted every attachment after the gap onto the
wrong game. The summary hid the timeout that went with it.

A4: a crashed game came through as an ordinary draw, which inflated draw rates
invisibly.

Run: python3 engine/tests/test_shim_alignment.py   (no network, no JVM)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shim_log_adapter import parse_shim_jsonl  # noqa: E402

P = ["Ai(1)-Alpha", "Ai(2)-Beta"]


def _meta():
    return json.dumps({"rec": "meta", "shim": "0.4.0", "format": "Commander",
                       "games": 3, "humanized": True, "players": P,
                       "decks": ["a.dck", "b.dck"]})


def _entries(game, turns=2):
    out = []
    for t in range(turns):
        out.append(json.dumps({"rec": "entry", "game": game, "seq": t,
                               "type": "TURN", "message": f"Turn {t + 1} (Ai(1)-Alpha)"}))
    return out


def _zone(game, card):
    return json.dumps({"rec": "zone", "game": game, "turn": 1, "card": card,
                       "cardId": 100 + game, "from": "Hand", "to": "Battlefield",
                       "fromPlayer": P[0], "toPlayer": P[0],
                       "types": "Creature", "pt": "2/2", "token": False})


def _agent(game, detail):
    return json.dumps({"rec": "agent", "game": game, "turn": 1, "player": P[0],
                       "event": "mull_keep", "detail": detail})


def _result(game, winner=None, draw=False, timed_out=False, error=None):
    r = {"rec": "result", "game": game, "draw": draw, "winner": winner,
         "turns": 10, "timedOut": timed_out, "ms": 1000}
    if error:
        r["error"] = True
        r["errorClass"] = error
    return json.dumps(r)


def test_a_lost_result_record_does_not_shift_the_others():
    # Game 1's result record is missing, exactly as a truncated flush leaves it.
    # Game 2 timed out. Before the fix, game 2's zones and its timeout landed
    # on the wrong game and the summary showed no timeout at all.
    lines = [_meta()]
    for g in (0, 1, 2):
        lines += _entries(g)
        lines.append(_zone(g, f"Card{g}"))
        lines.append(_agent(g, f"game{g}"))
    lines.append(_result(0, winner=P[0]))
    # game 1: NO result record
    lines.append(_result(2, draw=True, timed_out=True))

    r = parse_shim_jsonl("\n".join(lines))
    assert len(r["games"]) == 3, f"expected 3 games, got {len(r['games'])}"
    for i in range(3):
        zones = r["games"][i]["zones"]
        assert len(zones) == 1 and zones[0]["card"] == f"Card{i}", (i, zones)
        ev = r["games"][i]["agent_events"]
        assert ev and ev[0]["detail"] == f"game{i}", (i, ev)
    assert r["games"][1]["result"].get("missingResult") is True
    assert r["games"][2]["result"]["timedOut"] is True, r["games"][2]["result"]
    assert r["meta"]["games_missing_result"] == 1
    print("  a lost result record shifts nothing: OK")


def test_the_lost_game_is_not_scored_as_a_draw():
    lines = [_meta()]
    for g in (0, 1):
        lines += _entries(g)
    lines.append(_result(0, winner=P[0]))
    r = parse_shim_jsonl("\n".join(lines))
    s = r["summary"]
    assert s["games"] == 2, s          # the sample size stays honest
    assert s["draws"] == 0, s          # but the hole is not a draw
    assert s["quarantined"] == 1 and s["games_scored"] == 1, s
    # Win rate divides by games that produced a result, not by the hole.
    assert s["win_rates"][P[0]] == 1.0, s
    print("  a game with no result is quarantined, not counted as a draw: OK")


def test_a_crashed_game_is_flagged_and_never_scored():
    lines = [_meta()]
    for g in (0, 1):
        lines += _entries(g)
    lines.append(_result(0, winner=P[0]))
    lines.append(_result(1, winner=P[1], error="java.lang.OutOfMemoryError"))
    r = parse_shim_jsonl("\n".join(lines))
    g1 = r["games"][1]["result"]
    assert g1["error"] is True and g1["errorClass"] == "java.lang.OutOfMemoryError"
    # The crash carried a plausible winner; publishing it would have put a
    # fabricated result into the corpus.
    assert g1["winner"] is None and g1["draw"] is False, g1
    s = r["summary"]
    # Never credited: the suppressed winner does not even reach the wins map.
    assert s["wins"].get(P[1], 0) == 0, s
    assert s["draws"] == 0 and s["quarantined"] == 1, s
    assert r["meta"]["games_errored"] == 1
    print("  a crashed game is flagged and scores nothing: OK")


def test_a_clean_run_is_unchanged():
    lines = [_meta()]
    for g in (0, 1, 2):
        lines += _entries(g)
        lines.append(_zone(g, f"Card{g}"))
    lines.append(_result(0, winner=P[0]))
    lines.append(_result(1, winner=P[1]))
    lines.append(_result(2, draw=True))
    r = parse_shim_jsonl("\n".join(lines))
    s = r["summary"]
    assert s == {"games": 3, "draws": 1, "timeouts": 0,
                 "wins": {P[0]: 1, P[1]: 1},
                 "win_rates": {P[0]: 0.333, P[1]: 0.333}}, s
    assert "quarantined" not in s
    print("  a clean run summarizes exactly as before: OK")


def test_a_truncated_trailing_line_loses_one_record_not_the_run():
    lines = [_meta()]
    for g in (0, 1):
        lines += _entries(g)
    lines.append(_result(0, winner=P[0]))
    text = "\n".join(lines) + "\n" + _result(1, winner=P[1])[:40]  # torn mid-write
    r = parse_shim_jsonl(text)
    assert len(r["games"]) == 2, len(r["games"])
    assert r["games"][1]["result"].get("missingResult") is True
    print("  a torn trailing line costs one record, not the run: OK")


def main() -> None:
    for fn in (test_a_lost_result_record_does_not_shift_the_others,
               test_the_lost_game_is_not_scored_as_a_draw,
               test_a_crashed_game_is_flagged_and_never_scored,
               test_a_clean_run_is_unchanged,
               test_a_truncated_trailing_line_loses_one_record_not_the_run):
        fn()
    print("shim alignment: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
