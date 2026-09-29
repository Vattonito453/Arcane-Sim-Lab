#!/usr/bin/env python3
"""Deck telemetry for imported decks (repair plan WS11 task 8, UX problem 11).

Kess, Reanimator and Skrat's Revenge both read "No commander could be
identified" while the bundled decks resolved: meta.decks holds container
paths ("/data/decks/skrat_s_revenge_239c6293.dck") and _commander_of handed
that path to _find_deck, whose traversal rule refuses anything but a bare
filename, so only the bundled-deck fallback ever worked. And every deck's
only plan rows were "Charge counters" and "Proliferate", Atraxa-era metrics
counted across all seats. These checks pin:

  * an imported deck in MTG_DATA_DIR/decks, named by a container path,
    resolves its commander through _find_deck (the old lookup did not);
  * meta.commanders (run_sim / readapt) answers when the deck file is gone;
  * a Forge-style [Commander] line (count, |SET suffix, comment) reads the
    name Forge logs, so the cast count matches the log;
  * the charge-counter and proliferate rows are gone from the payload;
  * the cast count and the decided-game win rate on a small synthetic run.

Run: py engine/tests/test_telemetry.py   -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="simlab_telemetry_")
os.environ["MTG_DATA_DIR"] = _TMP
os.environ["MTG_EMBEDDED_WORKER"] = "0"

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import deck_telemetry  # noqa: E402
import mtg_engine  # noqa: E402

KESS, SKRAT = "Kess, Reanimator", "Skrat's Revenge"
PK, PS = f"Ai(1)-{KESS}", f"Ai(2)-{SKRAT}"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _write_decks():
    decks = Path(_TMP) / "decks"
    decks.mkdir(parents=True, exist_ok=True)
    (decks / "kess_reanimator_305b76d7.dck").write_text(
        "[metadata]\nName=Kess, Reanimator\n[Commander]\n# the face of the deck\n"
        "1 Kess, Dissident Mage|STX|1\n[Main]\n1 Sol Ring\n", encoding="utf-8")
    (decks / "skrat_s_revenge_239c6293.dck").write_text(
        "[metadata]\nName=Skrat's Revenge\n[Commander]\n1 The Unbeatable Squirrel Girl\n"
        "[Main]\n1 Sol Ring\n", encoding="utf-8")


def _run(commanders=None):
    def ev(action, raw):
        return {"action": action, "raw": raw}
    g1 = {"players": [PK, PS],
          "result": {"winner": PK, "draw": False, "raw": ""},
          "turns": [{"turn": 3, "active_player": PK, "events": [
              ev("stack_add", f"{PK} cast Kess, Dissident Mage"),
              ev("stack_add", f"{PS} cast Proliferate Test Spell"),
              ev("stack_resolve", "Put a charge counter on it, then proliferate."),
          ]}]}
    g2 = {"players": [PS, PK],
          "result": {"winner": PS, "draw": False, "raw": ""},
          "turns": [{"turn": 2, "active_player": PS, "events": [
              ev("stack_add", f"{PS} cast The Unbeatable Squirrel Girl")]}]}
    # Clock-cut, with the stale winner audit A16 describes: not decided.
    g3 = {"players": [PK, PS],
          "result": {"winner": PK, "draw": True, "timedOut": True, "raw": ""},
          "turns": []}
    meta = {"source": "rotated",
            "decks": ["/data/decks/kess_reanimator_305b76d7.dck",
                      "/data/decks/skrat_s_revenge_239c6293.dck"]}
    if commanders is not None:
        meta["commanders"] = commanders
    return {"meta": meta, "games": [g1, g2, g3]}


def test_imported_deck_resolves_through_find_deck():
    _write_decks()
    # The old lookup: the container path straight into _find_deck.
    check(mtg_engine._find_deck("/data/decks/kess_reanimator_305b76d7.dck") is None,
          "the traversal rule refuses a path (why the old lookup always missed)")
    rep = deck_telemetry.compute(_run(), "kess")
    check(rep["commander"] is not None, "an imported deck must resolve its commander")
    check(rep["commander"]["name"] == "Kess, Dissident Mage", rep["commander"])
    check(rep["commander"]["cast_rate"] == round(1 / 3, 3), rep["commander"])
    sk = deck_telemetry.compute(_run(), "skrat")
    check(sk["commander"]["name"] == "The Unbeatable Squirrel Girl", sk["commander"])
    print("  imported decks named by container paths resolve through _find_deck: OK")


def test_meta_commanders_when_the_file_is_gone():
    for f in (Path(_TMP) / "decks").glob("*.dck"):
        f.unlink()
    check(deck_telemetry.compute(_run(), "kess")["commander"] is None,
          "no file and no record: no commander, never a guess")
    rep = deck_telemetry.compute(_run({KESS: ["Kess, Dissident Mage"]}), "kess")
    check(rep["commander"]["name"] == "Kess, Dissident Mage", rep["commander"])
    print("  meta.commanders answers for a deck whose file is gone: OK")


def test_universal_rows_are_gone():
    _write_decks()
    rep = deck_telemetry.compute(_run(), "kess")
    check("engine" not in rep, "the charge-counter and proliferate rows are gone")
    blob = json.dumps(rep).lower()
    check("charge" not in blob and "proliferate_" not in blob, blob[:300])
    check(sorted(rep) == ["commander", "deaths", "decided", "deck", "games", "method",
                          "player_key", "source", "watched", "win_rate", "wins"], sorted(rep))
    print("  no charge-counter or proliferate rows: OK")


def test_decided_win_rate():
    _write_decks()
    rep = deck_telemetry.compute(_run(), "kess")
    check(rep["games"] == 3 and rep["decided"] == 2 and rep["wins"] == 1, rep)
    check(rep["win_rate"] == 0.5, "1 of 2 decided; the clock-cut 'win' is not a win")
    only_clock = _run()
    only_clock["games"] = only_clock["games"][2:]
    none = deck_telemetry.compute(only_clock, "kess")
    check(none["decided"] == 0 and none["win_rate"] is None, none)
    print("  the win rate divides by decided games: OK")


def test_served_route():
    _write_decks()
    mtg_engine.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    name = "sim_20260925_000000_tele_rotated.json"
    (mtg_engine.RESULTS_DIR / name).write_text(json.dumps(_run()), encoding="utf-8")
    rep = mtg_engine._read_result_telemetry(name, "skrat")
    check(rep["commander"]["name"] == "The Unbeatable Squirrel Girl", rep)
    check(rep["file"] == name and "engine" not in rep, rep)
    print("  GET /results/{file}/telemetry serves the imported deck's commander: OK")


def main():
    test_imported_deck_resolves_through_find_deck()
    test_meta_commanders_when_the_file_is_gone()
    test_universal_rows_are_gone()
    test_decided_win_rate()
    test_served_route()
    print("test_telemetry: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
