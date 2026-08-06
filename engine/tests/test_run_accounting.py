#!/usr/bin/env python3
"""Run sizing, timeout ceilings, salvage and the job-state guard.

Covers audit A14 (the ceiling was a flat 2 h that the largest allowed request
could not finish inside, discarding every completed game when it fired), A5
(a lost rotation was a stderr line and the merged result still claimed a full
sweep), A27 (requested and played games disagreed on every surface) and A17
(finish() had no state guard, so a reaped job could be resurrected).

Run: python3 engine/tests/test_run_accounting.py   (no network, no JVM)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mtg_engine  # noqa: E402
import run_sim  # noqa: E402
import validity  # noqa: E402


# ---------------------------------------------------------------- A27

def test_every_rotation_gets_the_same_number_of_games():
    for requested in range(1, 40):
        split = run_sim.plan_games(requested, 4)
        assert len(set(split)) == 1, (requested, split)
        assert sum(split) >= requested, (requested, split)
        # Never more than one extra rotation's worth.
        assert sum(split) - requested < 4, (requested, split)
    print("  seats stay balanced for every request size: OK")


def test_the_played_total_is_a_whole_number_of_rotations():
    assert run_sim.plan_games(10, 4) == [3, 3, 3, 3]       # was 8 played for 10 asked
    assert run_sim.plan_games(63, 4) == [16, 16, 16, 16]   # was 60
    assert run_sim.plan_games(1, 4) == [1, 1, 1, 1]        # was 4, silently
    assert run_sim.plan_games(16, 4) == [4, 4, 4, 4]
    print("  the played total is always whole rotations: OK")


def test_a_cap_is_respected():
    split = run_sim.plan_games(64, 4, cap=64)
    assert sum(split) == 64, split
    split = run_sim.plan_games(63, 4, cap=64)
    assert sum(split) <= 64, split
    print("  rounding up never breaches the cap: OK")


def test_one_deck_still_works():
    assert run_sim.plan_games(5, 1) == [5]
    assert run_sim.plan_games(0, 1) == [1]
    print("  a single-rotation run is unchanged: OK")


# ---------------------------------------------------------------- A14

def test_the_ceiling_can_actually_fit_the_work():
    # The bug in one assertion: 16 games at a 900 s clock is 14,400 s of
    # legitimate worst-case play, and the old flat ceiling was 7,200 s.
    os.environ.pop("MTG_SIM_TIMEOUT_SECONDS", None)
    for games, rotations in ((16, 4), (64, 4), (8, 2), (1, 4)):
        played = sum(run_sim.plan_games(games, rotations))
        ceiling = mtg_engine.sim_timeout_seconds(games, rotations)
        assert ceiling > played * mtg_engine.SIM_CLOCK_SECONDS, (games, ceiling)
    assert mtg_engine.sim_timeout_seconds(16, 4) > 2 * 3600
    print("  the ceiling exceeds worst-case play for every allowed size: OK")


def test_an_explicit_override_still_wins():
    os.environ["MTG_SIM_TIMEOUT_SECONDS"] = "123"
    try:
        assert mtg_engine.sim_timeout_seconds(64, 4) == 123.0
    finally:
        os.environ.pop("MTG_SIM_TIMEOUT_SECONDS", None)
    print("  an operator override is honored: OK")


def test_the_estimate_is_far_below_the_ceiling():
    # They answer different questions: one is "what should I expect", the
    # other is "when do we conclude it hung". Conflating them is what made a
    # normal long run look like a failure.
    low, high = mtg_engine.estimate_sim_seconds(16, 4)
    assert 0 < low < high < mtg_engine.sim_timeout_seconds(16, 4)
    print("  the typical estimate is not the hang ceiling: OK")


def test_salvage_rebuilds_a_result_from_finished_rotations(tmp: Path):
    # Two rotation logs on disk, as a killed run leaves behind.
    for rot, wins in ((0, ["Ai(1)-A", "Ai(2)-B"]), (1, ["Ai(3)-C"])):
        lines = []
        for i, w in enumerate(wins, 1):
            lines.append(f"Turn: 1 ({w})")
            lines.append(f"Game Result: Game {i} ended in 42000 ms. {w} has won!")
        (tmp / f"forge_raw_kt_rot{rot}.log").write_text("\n".join(lines), encoding="utf-8")

    out = run_sim.salvage(tmp, "kt", decks=["a.dck", "b.dck", "c.dck", "d.dck"],
                          games_expected=8)
    assert out is not None and out.is_file()
    data = json.loads(out.read_text())
    assert len(data["games"]) == 3, data["summary"]
    m = data["meta"]
    assert m["incomplete"] is True and m["salvaged_from_kill"] is True
    # Rotations EXPECTED, not the number of logs that survived: reporting
    # "2 of 2 finished" for a run that lost half of them is the opposite of
    # what a salvaged result has to say.
    assert m["rotations"] == 4 and m["rotations_completed"] == 2, m
    assert m["games_expected"] == 8 and m["games_played"] == 3, m
    print("  a killed run's finished rotations are recovered: OK")


def test_a_salvaged_run_cannot_be_used_for_ranking(tmp: Path):
    (tmp / "forge_raw_kt2_rot0.log").write_text(
        "Turn: 1 (Ai(1)-A)\nGame Result: Game 1 ended in 42000 ms. Ai(1)-A has won!",
        encoding="utf-8")
    out = run_sim.salvage(tmp, "kt2", decks=["a.dck", "b.dck", "c.dck", "d.dck"])
    v = validity.assess(json.loads(out.read_text()))
    assert v["quality"] == validity.POLLUTED, v
    assert "incomplete_run" in v["flags"], v
    assert v["usable_for_ranking"] is False
    print("  an incomplete run is kept but never ranked: OK")


def test_salvage_returns_none_when_there_is_nothing_to_recover(tmp: Path):
    assert run_sim.salvage(tmp, "nothinghere") is None
    print("  salvage with no logs is a no-op, not a crash: OK")


# ---------------------------------------------------------------- A5

def test_rotation_meta_records_the_hole():
    m = run_sim._rotation_meta(16, [4, 4, 4, 4], [4, 4, 0, 4])
    assert m["incomplete"] is True
    assert m["games_played"] == 12 and m["games_expected"] == 16
    assert m["rotations_completed"] == 3
    print("  a lost rotation is recorded, not smoothed over: OK")


def test_a_complete_run_is_not_flagged():
    m = run_sim._rotation_meta(16, [4, 4, 4, 4], [4, 4, 4, 4])
    assert m["incomplete"] is False and m["games_played"] == 16
    print("  a complete run stays unflagged: OK")


# ---------------------------------------------------------------- A17

def test_finish_only_completes_a_running_job(tmp: Path):
    import jobqueue  # noqa: PLC0415
    jobqueue.DATA_DIR = tmp
    jobqueue.DB_PATH = tmp / "jobs.db"   # _conn() applies the schema on connect

    jid = jobqueue.enqueue({"decks": ["a.dck"], "games": 1})
    assert jobqueue.finish(jid, result={"summary": {}}) is False, \
        "a queued job is not running and must not be completed"
    claimed = jobqueue.claim()
    assert claimed and claimed["id"] == jid
    assert jobqueue.finish(jid, result={"summary": {"games": 1}}) is True
    # The resurrection: reap_stale marked it error, then the worker returned.
    # Second finish must be refused, or the user is told a job died and then
    # silently told it did not.
    assert jobqueue.finish(jid, error="worker was lost") is False
    assert jobqueue.get(jid)["state"] == "done"
    print("  finish() refuses a job that is no longer running: OK")


def main() -> None:
    plain = (test_every_rotation_gets_the_same_number_of_games,
             test_the_played_total_is_a_whole_number_of_rotations,
             test_a_cap_is_respected,
             test_one_deck_still_works,
             test_the_ceiling_can_actually_fit_the_work,
             test_an_explicit_override_still_wins,
             test_the_estimate_is_far_below_the_ceiling,
             test_rotation_meta_records_the_hole,
             test_a_complete_run_is_not_flagged)
    needs_tmp = (test_salvage_rebuilds_a_result_from_finished_rotations,
                 test_a_salvaged_run_cannot_be_used_for_ranking,
                 test_salvage_returns_none_when_there_is_nothing_to_recover,
                 test_finish_only_completes_a_running_job)
    for fn in plain:
        fn()
    for fn in needs_tmp:
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("run accounting: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
