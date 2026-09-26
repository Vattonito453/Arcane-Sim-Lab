#!/usr/bin/env python3
"""GET /estimate: the one place the web gets a sim's duration and game count.

Before this route the web kept its own table (format.ts SECONDS_PER_GAME,
measured on stock Forge) and told a player "about 14 min" for a 4-deck,
8-game job that took 55 min 56 s; one click later the run page switched to
the engine's range (tasks/26-ux-review.md, problem 4). These checks pin the
contract that fixes it:

  * the played count is run_sim's own rounding (whole seat rotations), for
    every size the API accepts, so the button can never promise 16 games and
    play 18;
  * the range is exactly what /sim-status reports once the job is queued;
  * whole-rotation requests (all /new offers) are never rounded;
  * the hang ceiling never leaks into a figure meant for a person;
  * the documented "40 to 105 minutes for 16 games" (CLAUDE.md) still holds,
    so changing TYPICAL_GAME_SECONDS fails here until the docs move with it;
  * the HTTP route answers and refuses sizes POST /simulate would refuse.

Run: py engine/tests/test_estimate.py   (no network beyond 127.0.0.1, no JVM)
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# A throwaway data dir and no embedded worker, set before the engine imports
# read them, so the in-process server below touches nothing real.
_TMP = tempfile.mkdtemp(prefix="simlab_estimate_")
os.environ["MTG_DATA_DIR"] = _TMP
os.environ["MTG_EMBEDDED_WORKER"] = "0"
os.environ["MTG_BIND"] = "127.0.0.1"
os.environ.pop("MTG_SIM_ROTATE", None)
os.environ.pop("MTG_SIM_TIMEOUT_SECONDS", None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mtg_engine  # noqa: E402
import run_sim  # noqa: E402


def test_played_count_is_run_sims_rounding():
    for decks in (2, 3, 4):
        for games in range(1, mtg_engine.SIM_MAX_GAMES + 1):
            est = mtg_engine.sim_estimate(decks, games)
            played = sum(run_sim.plan_games(games, decks))
            assert est["games_to_play"] == played, (decks, games, est, played)
            assert est["rotations"] == decks, (decks, games, est)
            assert est["games_requested"] == games, est
    # The CLAUDE.md example, and the UX review's "3 decks will play 18".
    assert mtg_engine.sim_estimate(4, 10)["games_to_play"] == 12
    assert mtg_engine.sim_estimate(3, 16)["games_to_play"] == 18
    print("  played count matches run_sim.plan_games for every accepted size: OK")


def test_whole_rotations_are_never_rounded():
    # /new offers only these, and puts the count on the button.
    for decks in (2, 3, 4):
        for starts in (1, 2, 4, 8):
            est = mtg_engine.sim_estimate(decks, decks * starts)
            assert est["games_to_play"] == decks * starts, (decks, starts, est)
    print("  whole-rotation requests play exactly what was asked: OK")


def test_range_is_what_the_run_page_will_show():
    for decks in (2, 3, 4):
        for games in (1, 4, 10, 16, 32, 64):
            est = mtg_engine.sim_estimate(decks, games)
            prog = mtg_engine._job_progress(
                {"decks": ["x.dck"] * decks, "games": games, "state": "queued"})
            assert est["typical_seconds"] == prog["typical_seconds"], (decks, games)
            assert est["games_to_play"] == prog["expected_games"], (decks, games)
            low, high = est["typical_seconds"]
            assert isinstance(low, int) and isinstance(high, int), est
            assert 0 < low < high, est
            # A typical range, far below the hang ceiling it must never be.
            assert high < mtg_engine.sim_timeout_seconds(games, decks), est
    print("  range equals /sim-status's for the same job, below the ceiling: OK")


def test_no_ceiling_in_a_figure_for_people():
    est = mtg_engine.sim_estimate(4, 64)
    assert set(est) == {"decks", "games_requested", "games_to_play", "rotations",
                        "typical_seconds"}, sorted(est)
    print("  the payload carries no timeout ceiling: OK")


def test_documented_sixteen_game_range_holds():
    # CLAUDE.md: "roughly 40-105 min for a 4-deck 16-game gauntlet". The web
    # rounds low down and high up to whole minutes, so this is what it shows.
    low, high = mtg_engine.sim_estimate(4, 16)["typical_seconds"]
    assert (low // 60, -(-high // 60)) == (40, 105), (low, high)
    print("  4 decks, 16 games: usually 40 to 105 minutes, as documented: OK")


def test_rotation_off_plays_the_request():
    os.environ["MTG_SIM_ROTATE"] = "0"
    try:
        est = mtg_engine.sim_estimate(4, 10)
        assert est["rotations"] == 1 and est["games_to_play"] == 10, est
    finally:
        os.environ.pop("MTG_SIM_ROTATE", None)
    print("  with rotation off, nothing is rounded: OK")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _get(base: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_route():
    port = _free_port()
    threading.Thread(target=mtg_engine.serve, args=(port,), daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):  # the KB loads before the socket binds
        try:
            urllib.request.urlopen(base + "/health", timeout=2).read()
            break
        except OSError:
            time.sleep(0.1)
    st, body = _get(base, "/estimate?decks=3&games=16")
    assert st == 200, (st, body)
    assert body == mtg_engine.sim_estimate(3, 16), body
    assert body["games_to_play"] == 18, body
    for bad in ("", "?decks=4", "?games=16", "?decks=1&games=16", "?decks=5&games=16",
                "?decks=4&games=0", f"?decks=4&games={mtg_engine.SIM_MAX_GAMES + 1}",
                "?decks=four&games=16"):
        st, body = _get(base, "/estimate" + bad)
        assert st == 400 and "error" in body, (bad, st, body)
    # The route is exactly /estimate: a longer path is not an alias for it.
    st, body = _get(base, "/estimate/anything?decks=4&games=16")
    assert st == 404, (st, body)
    print("  GET /estimate answers, and refuses sizes /simulate would refuse: OK")


if __name__ == "__main__":
    test_played_count_is_run_sims_rounding()
    test_whole_rotations_are_never_rounded()
    test_range_is_what_the_run_page_will_show()
    test_no_ceiling_in_a_figure_for_people()
    test_documented_sixteen_game_range_holds()
    test_rotation_off_plays_the_request()
    test_http_route()
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)
    print("estimate: ALL ASSERTIONS PASSED")
