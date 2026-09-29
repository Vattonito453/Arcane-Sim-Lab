#!/usr/bin/env python3
"""board_from_game.py: a scenario board from a real shim game's records.

    py studies/scenarios/tests/test_board_from_game.py

The JSONL is synthetic but in the shape the shim writes (meta, entry, zone,
tap). It checks the snapshot point (the end of the turn's precombat main
phase), tapped state from tap records, a card that ENTERED tapped (no tap
record; Forge fires none), sickness for what the active seat put down this
turn, life from Forge's log, and a seat already at 0 written at -1.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import board_from_game as B  # noqa: E402

A, Bs, C = "Ai(1)-alpha", "Ai(2)-bravo", "Ai(3)-charlie"


def game() -> list[dict]:
    recs = [{"rec": "meta", "players": [A, Bs, C],
             "decks": ["studies/x/alpha.dck", "studies/x/bravo.dck", "studies/x/charlie.dck"],
             "agents": ["stock", "stock", "stock"], "shim": "0.17.1"}]
    seq = iter(range(10 ** 6))

    def entry(t, m):
        recs.append({"rec": "entry", "game": 0, "seq": next(seq), "type": t, "message": m})

    def zone(turn, phase, cid, card, frm, to, who, types="Land"):
        recs.append({"rec": "zone", "game": 0, "turn": turn, "phase": phase, "cardId": cid, "card": card,
                     "from": frm, "to": to, "fromPlayer": who, "toPlayer": who if to != "Graveyard" else who,
                     "types": types, "pt": "", "token": False})

    def tap(turn, phase, cid, card, tapped):
        recs.append({"rec": "tap", "game": 0, "turn": turn, "phase": phase, "cardId": cid, "card": card,
                     "tapped": tapped})

    entry("TURN", f"Turn 1 ({A})")
    zone(1, "MAIN1", 1, "Island", "Hand", "Battlefield", A)
    entry("TURN", f"Turn 2 ({Bs})")
    zone(2, "MAIN1", 2, "Breeding Pool", "Hand", "Battlefield", Bs)        # entered tapped: no tap record
    zone(2, "MAIN1", 3, "Forest", "Library", "Battlefield", Bs)
    tap(2, "MAIN2", 3, "Forest", True)                                      # tapped for mana
    zone(2, "MAIN2", 5, "Temple of Mystery", "Hand", "Battlefield", Bs)    # entered tapped, leaves before untapping
    entry("LIFE", f"Life: {Bs} 40 > 35")
    entry("LIFE", f"Life: {C} 3 > 0")
    entry("TURN", f"Turn 3 ({A})")
    entry("PHASE", f"{A}'s Main phase, precombat")
    zone(3, "MAIN1", 4, "Godo, Bandit Warlord", "Hand", "Battlefield", A, types="Legendary Creature Human")
    entry("PHASE", f"{A}'s Beginning of Combat Step")
    entry("LIFE", f"Life: {Bs} 35 > 30")                                   # after the snapshot
    # after the snapshot point
    tap(3, "COMBAT_DECLARE_ATTACKERS", 4, "Godo, Bandit Warlord", True)
    zone(3, "COMBAT_END", 5, "Temple of Mystery", "Battlefield", "Graveyard", Bs)
    entry("TURN", f"Turn 4 ({Bs})")
    tap(4, "UNTAP", 2, "Breeding Pool", False)
    tap(4, "UNTAP", 3, "Forest", False)
    recs.append({"rec": "result", "game": 0, "winner": A, "turns": 4})
    for r in recs[1:]:
        r.setdefault("game", 0)
    return recs


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cell.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in game()) + "\n", encoding="utf-8")
        meta, recs = B.load_game(p, 0)
        snap = B.snapshot(recs, 3)
        assert snap["tapped"].get(3) is True, "a tap record before the snapshot"
        assert snap["tapped"].get(2) is True and snap["entered_tapped"] == [2], snap
        assert not snap["tapped"].get(5), "left before untapping: unknown, written untapped"
        assert not snap["tapped"].get(4), "Godo's attack tap is after the snapshot"
        assert not snap["tapped"].get(1)
        print("  snapshot: tap records, a card that entered tapped, the cut before combat: OK")

        sc = B.build(p, 0, 3, "t", None)
        seats = {i: s for i, s in enumerate(sc["seats"])}
        bf = {c["card"]: c for s in seats.values() for c in s["battlefield"]}
        assert bf["Breeding Pool"].get("tapped") is True and bf["Forest"].get("tapped") is True
        assert "tapped" not in bf["Temple of Mystery"] and "tapped" not in bf["Island"]
        assert bf["Godo, Bandit Warlord"].get("sick") is True, "the active seat's creature entered this turn"
        assert "sick" not in bf["Forest"]
        assert seats[1]["life"] == 35, "life walked to the snapshot, not past it"
        assert seats[2]["life"] == -1, "a seat already at 0 is written at -1 (GameState cannot load 0)"
        assert sc["active"] == 0 and sc["turn"] == 3 and sc["phase"] == "MAIN1"
        notes = " ".join(sc["notes"])
        assert f"Breeding Pool ({Bs})" in notes and "entered tapped" in notes, notes
        assert "written at -1" in notes
        print("  build: tapped and sick flags, life at the snapshot, a lost seat at -1, notes: OK")
    print("board_from_game: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
