#!/usr/bin/env python3
"""Combo-line analysis: path-aware board reads, and no "fired" verdict.

Two defects this pins (repair plan WS11 task 2, UX review problem 2):

1. analysis.py always rebuilt the board with the STDOUT inference path, even on
   shim runs whose games carry the zone stream, and its note said "inferred"
   on every run. A shim run's combo table could then contradict its own replay
   board (Clock of Omens "never available" while the replay showed it tutored
   onto the battlefield). Shim games must be read from zone records, and the
   note must say which path a report is on.
2. A line whose deck merely won later, by any means, was read as "fired" and
   the results page badged it as a line the AI could fire, with meaningful
   results. The reading is gone; the count survives unbadged as
   `won_after_assembly`.

Run: py engine/tests/test_analysis_combos.py   (no network, no JVM)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analysis  # noqa: E402
import combos  # noqa: E402

A = "Ai(1)-Alpha Test"
B = "Ai(2)-Beta Test"

LINE = {"id": "1-2", "cards": ["Piece One", "Piece Two"],
        "produces": ["Infinite colorless mana"],
        "description": "Tap Piece One.\nUntap it with Piece Two.\nRepeat.",
        "mana_needed": "", "prerequisites": ""}
NEVER = {"id": "3-4", "cards": ["Absent Card", "Other Absent Card"],
         "produces": ["Infinite ETB"], "description": "", "mana_needed": "",
         "prerequisites": ""}


def _dck(folder: Path, stem: str, name: str) -> str:
    body = (f"[metadata]\nName={name}\n[Commander]\n1 Commander Card\n"
            "[Main]\n1 Piece One\n1 Piece Two\n1 Absent Card\n"
            "1 Other Absent Card\n95 Forest\n")
    (folder / f"{stem}.dck").write_text(body, encoding="utf-8")
    return f"{stem}.dck"


def _turns(n: int, events: dict[int, list[dict]] | None = None) -> list[dict]:
    events = events or {}
    return [{"turn": t, "active_player": A if t % 2 else B,
             "events": events.get(t, [])} for t in range(1, n + 1)]


def _z(turn, card, cid, frm, to, player):
    return {"turn": turn, "card": card, "cardId": cid, "from": frm, "to": to,
            "fromPlayer": player, "toPlayer": player, "types": "Artifact",
            "pt": "", "token": False}


def _zone_game(winner: str) -> dict:
    """Pieces enter on turns 3 and 5 by zone record only; the text log is
    empty, so the stdout path would find nothing. Turns 6 and 7 carry no zone
    record at all, which is where a snapshot-per-record board used to lose
    the turns the line sat online. Piece One leaves on turn 8."""
    return {
        "players": [A, B],
        "turns": _turns(9),
        "zones": [
            _z(0, "Piece One", 11, "Library", "Hand", A),
            _z(3, "Piece One", 11, "Hand", "Battlefield", A),
            _z(4, "Forest", 12, "Hand", "Battlefield", B),
            _z(5, "Piece Two", 13, "Hand", "Battlefield", A),
            _z(8, "Piece One", 11, "Battlefield", "Graveyard", A),
        ],
        "result": {"winner": winner, "draw": False, "duration_ms": 1000,
                   "raw": f"{winner} has won!"},
    }


def _stdout_game(winner: str) -> dict:
    """The same pieces, seen only through the text log (a stock Forge run)."""
    ev = {
        2: [{"seq": 1, "action": "land_drop",
             "raw": f"{A} played Piece One (101)."}],
        4: [{"seq": 2, "action": "land_drop",
             "raw": f"{A} played Piece Two (102)."}],
    }
    return {"players": [A, B], "turns": _turns(6, ev),
            "result": {"winner": winner, "draw": False, "duration_ms": 1000,
                       "raw": f"{winner} has won!"}}


def _run(games: list[dict], deck_dir: Path, files: list[str]) -> dict:
    result = {"file": "sim_test.json", "meta": {"decks": files},
              "games": games}
    return analysis.analyse(result, deck_dirs=[deck_dir], fetch=False)


def main() -> None:
    # Spellbook is stubbed: this test is about what analysis does with lines,
    # not about fetching them.
    combos.combos_for_dck = lambda p, fetch=True: {
        "included": [dict(LINE), dict(NEVER)], "almost_included": [{}]}

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        files = [_dck(d, "alpha", "Alpha Test"), _dck(d, "beta", "Beta Test")]

        # ---- shim run: the board is read from zone records -------------
        rep = _run([_zone_game(A)], d, files)
        assert rep["version"] == analysis.ANALYSIS_VERSION >= 5, rep["version"]
        assert rep["basis"] == "zone_stream", rep["basis"]
        note = rep["note"]
        assert "zone records" in note, note
        assert "inferred" not in note, note
        assert "—" not in note, "UI copy must not carry an em dash"

        line = next(c for c in rep["decks"]["Alpha Test"]["combos"]
                    if c["id"] == "1-2")
        g = line["games"][0]
        assert g["assembled_turn"] == 5, g
        # Turns 5, 6 and 7 online: 6 and 7 had no zone record and are carried
        # forward; Piece One left on turn 8.
        assert g["online_turns"] == 3, g
        assert g["pieces"] == {"Piece One": 3, "Piece Two": 5}, g["pieces"]
        assert line["assembled_games"] == 1
        assert line["won_after_assembly"] == 1
        assert line["converted_games"] == line["won_after_assembly"]
        assert line["reading"] == "assembled", line["reading"]
        assert line["idle_online_turns"] == 0      # it won that game

        # The same deck on the losing side: pieces together, no win.
        rep_l = _run([_zone_game(B)], d, files)
        lost = next(c for c in rep_l["decks"]["Alpha Test"]["combos"]
                    if c["id"] == "1-2")
        assert lost["won_after_assembly"] == 0
        assert lost["reading"] == "assembled", lost["reading"]
        assert lost["idle_online_turns"] == 3

        # ---- stdout run: inference, and the note keeps its rate ---------
        rep_s = _run([_stdout_game(A)], d, files)
        assert rep_s["basis"] == "inferred", rep_s["basis"]
        assert "inferred" in rep_s["note"] and "83-86%" in rep_s["note"]
        assert "zone records" not in rep_s["note"]
        s_line = next(c for c in rep_s["decks"]["Alpha Test"]["combos"]
                      if c["id"] == "1-2")
        assert s_line["games"][0]["assembled_turn"] == 4, s_line["games"][0]
        assert s_line["won_after_assembly"] == 1

        # ---- mixed run: say both, with the count ------------------------
        rep_m = _run([_zone_game(A), _stdout_game(B)], d, files)
        assert rep_m["basis"] == "mixed", rep_m["basis"]
        assert "1 of 2 games" in rep_m["note"], rep_m["note"]

        # ---- no reading anywhere may be the old verdict -----------------
        allowed = {"assembled", "sample_too_small", "not_assembled"}
        for r in (rep, rep_l, rep_s, rep_m):
            for deck in r["decks"].values():
                for c in deck["combos"]:
                    assert c["reading"] in allowed, c["reading"]
                    assert c["reading"] != "fired"
        never = next(c for c in rep["decks"]["Alpha Test"]["combos"]
                     if c["id"] == "3-4")
        assert never["assembled_games"] == 0
        assert never["reading"] == "sample_too_small", never

        # turn_boards on a stdout game is the old per-turn reconstruction.
        tb = analysis.turn_boards(_stdout_game(A))
        assert [s["turn"] for s in tb] == [1, 2, 3, 4, 5, 6], tb
        # On a zone game it covers every game turn, pregame dropped.
        tz = analysis.turn_boards(_zone_game(A))
        assert [s["turn"] for s in tz] == list(range(1, 10)), tz

    print("ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
