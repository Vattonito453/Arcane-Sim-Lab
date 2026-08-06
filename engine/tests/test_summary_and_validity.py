#!/usr/bin/env python3
"""Timeout accounting (audit A16) and the pollution gate (audit A25).

A16: a `timeouts` counter shipped on 2026-08-03 and did not work. Two reasons,
both covered here. `_summarize_by_deck` is the summarizer the DEFAULT path uses
— every rotated run rebuilds its merged summary there — and it had no timeouts
key at all, so the per-rotation counts were computed and then thrown away. And
both summarizers still CREDITED the winner on a game the clock had cut off, so
re-parsing a polluted file re-minted the fake win it was being re-parsed to
remove.

A25: nothing downstream could tell a polluted run from a good one. These pin
the verdicts, and in particular that severity is the WORST flag present rather
than the last one evaluated.

Run: python3 engine/tests/test_summary_and_validity.py   (no network, no JVM)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import forge_log_adapter  # noqa: E402
import run_sim  # noqa: E402
import validity  # noqa: E402

A, B = "Ai(1)-Alpha Deck", "Ai(2)-Beta Deck"


def _game(**result):
    return {"players": [A, B], "result": result}


# ---------------------------------------------------------------- A16

def test_rotated_summary_carries_timeouts():
    s = run_sim._summarize_by_deck([
        _game(winner=A, draw=False),
        _game(draw=True, timedOut=True),
    ])
    assert s["timeouts"] == 1, s
    print("  _summarize_by_deck reports timeouts at all: OK")


def test_a_clock_cut_game_never_credits_its_winner():
    # The exact shape of the bug: Forge's outcome object names a winner on a
    # game the clock ended. 83% of 4-pod games looked like this.
    s = run_sim._summarize_by_deck([_game(winner=A, draw=False, timedOut=True)])
    assert s["wins"]["Alpha Deck"] == 0, s
    assert s["draws"] == 1, s
    assert s["timeouts"] == 1, s
    assert s["win_rates"]["Alpha Deck"] == 0.0, s
    print("  a timed-out game is a draw, not a win: OK")


def test_the_same_holds_in_the_stock_summarizer():
    s = forge_log_adapter.summarize([_game(winner=A, draw=False, timedOut=True)])
    assert s["wins"][A] == 0, s
    assert s["draws"] == 1 and s["timeouts"] == 1, s
    print("  forge_log_adapter.summarize agrees: OK")


def test_a_timed_out_draw_is_counted_once():
    # timedOut and draw are both set on shim results; the draw must not
    # double-count now that the timeout branch also increments it.
    s = run_sim._summarize_by_deck([_game(draw=True, timedOut=True)])
    assert s["draws"] == 1, s
    print("  a timed-out draw counts once, not twice: OK")


def test_ordinary_runs_are_unaffected():
    s = run_sim._summarize_by_deck([
        _game(winner=A, draw=False), _game(winner=A, draw=False),
        _game(winner=B, draw=False), _game(draw=True),
    ])
    assert s == {"games": 4, "draws": 1, "timeouts": 0,
                 "wins": {"Alpha Deck": 2, "Beta Deck": 1},
                 "win_rates": {"Alpha Deck": 0.5, "Beta Deck": 0.25}}, s
    print("  a clean run summarizes exactly as before: OK")


# ---------------------------------------------------------------- A25

def _result(games, **meta):
    base = {"source": "rotated", "humanized": True, "clock": 900}
    base.update(meta)
    return {"meta": base, "games": games}


def test_a_good_run_is_clean():
    v = validity.assess(_result([
        _game(winner=A, draw=False, duration_ms=120_000, timedOut=False),
        _game(draw=True, duration_ms=900_001, timedOut=True),
    ]))
    assert v["quality"] == validity.CLEAN, v
    assert v["usable_for_ranking"] is True, v
    # A timeout is not itself pollution: it is a draw, honestly recorded.
    assert v["timed_out"] == 1 and v["clock_cut_wins"] == 0, v
    print("  a rotated run with an honest timeout is clean: OK")


def test_a_recorded_fake_win_is_polluted():
    v = validity.assess(_result([
        _game(winner=A, draw=False, duration_ms=900_002, timedOut=True)]))
    assert v["quality"] == validity.POLLUTED, v
    assert "clock_cut_wins" in v["flags"], v
    assert v["usable_for_ranking"] is False, v
    print("  a clock-cut game recorded as a win is polluted: OK")


def test_the_duration_signature_catches_files_with_no_timedOut_flag():
    # Pre-shim stock runs have no timedOut key; the audit's verified signature
    # is duration_ms >= clock * 1000.
    v = validity.assess(_result([
        _game(winner=A, draw=False, duration_ms=900_500)], clock=900))
    assert v["quality"] == validity.POLLUTED, v
    print("  duration past a known clock is caught without the flag: OK")


def test_without_a_recorded_clock_the_verdict_is_only_suspect():
    r = _result([_game(winner=A, draw=False, duration_ms=240_002)])
    del r["meta"]["clock"]
    v = validity.assess(r)
    assert v["quality"] == validity.SUSPECT, v
    assert "suspected_clock_cut_wins" in v["flags"], v
    print("  an inferred clock downgrades to suspect, not polluted: OK")


def test_a_natural_game_is_not_mistaken_for_a_clock_cut():
    r = _result([_game(winner=A, draw=False, duration_ms=615_000)])
    del r["meta"]["clock"]
    assert validity.assess(r)["quality"] == validity.CLEAN, validity.assess(r)
    print("  a long but natural game is left alone: OK")


def test_not_rotated_is_polluted_on_its_own():
    v = validity.assess(_result([_game(winner=A, draw=False, duration_ms=1000)],
                                source="single"))
    assert v["quality"] == validity.POLLUTED and "not_rotated" in v["flags"], v
    print("  a non-rotated run cannot be ranked: OK")


def test_severity_is_the_worst_flag_not_the_last_one():
    # The regression this guards: "suspect" was assigned first and a later
    # "polluted" flag then found quality != CLEAN and left it alone, so the
    # runs with the MOST wrong with them reported as the milder verdict.
    r = _result([_game(winner=A, draw=False, duration_ms=240_002)],
                source="single")
    del r["meta"]["clock"]
    v = validity.assess(r)
    assert "suspected_clock_cut_wins" in v["flags"] and "not_rotated" in v["flags"], v
    assert v["quality"] == validity.POLLUTED, v
    print("  severity is the worst flag present: OK")


def test_a_mixed_pod_is_flagged_as_a_different_experiment():
    v = validity.assess(_result([_game(winner=A, draw=False, duration_ms=1000)],
                                humanized_by_rotation=[True, True, False, True]))
    assert v["quality"] == validity.SUSPECT and "mixed_pilot" in v["flags"], v
    print("  a pod where some seats fell back to stock is flagged: OK")


def test_a_run_predating_the_pilot_flag_is_suspect():
    r = _result([_game(winner=A, draw=False, duration_ms=1000)])
    del r["meta"]["humanized"]
    v = validity.assess(r)
    assert v["quality"] == validity.SUSPECT and "unknown_pilot" in v["flags"], v
    print("  a run that cannot say which agent ran is suspect: OK")


def test_a_malformed_file_does_not_crash_the_gate():
    for bad in ({}, {"meta": None, "games": None}, {"games": [None, {}]}):
        v = validity.assess(bad)
        assert v["quality"] in (validity.CLEAN, validity.SUSPECT, validity.POLLUTED)
    print("  a malformed result yields a verdict, not an exception: OK")


def main() -> None:
    for fn in (test_rotated_summary_carries_timeouts,
               test_a_clock_cut_game_never_credits_its_winner,
               test_the_same_holds_in_the_stock_summarizer,
               test_a_timed_out_draw_is_counted_once,
               test_ordinary_runs_are_unaffected,
               test_a_good_run_is_clean,
               test_a_recorded_fake_win_is_polluted,
               test_the_duration_signature_catches_files_with_no_timedOut_flag,
               test_without_a_recorded_clock_the_verdict_is_only_suspect,
               test_a_natural_game_is_not_mistaken_for_a_clock_cut,
               test_not_rotated_is_polluted_on_its_own,
               test_severity_is_the_worst_flag_not_the_last_one,
               test_a_mixed_pod_is_flagged_as_a_different_experiment,
               test_a_run_predating_the_pilot_flag_is_suspect,
               test_a_malformed_file_does_not_crash_the_gate):
        fn()
    print("timeouts + validity: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
