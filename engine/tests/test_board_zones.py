#!/usr/bin/env python3
"""Board reconstruction from the shim's zone stream.

Forge's stdout log reports cards LEAVING the battlefield and never entering,
so the text path has to infer membership (86.5% exit match, and the misses are
overwhelmingly tokens whose only mention anywhere is their own death). The shim
taps GameEventCardChangeZone instead and reports both directions, keyed by
Forge's card id and — since shim 0.3.0 — stamped with the card's core types,
net P/T and token flag. That turns the board from a guess into a read.

These tests pin the properties that matter: the zone path is exact, it types
tokens without Scryfall, it carries P/T, and neither older shim logs nor
stdout-only runs regress.

Run: python3 engine/tests/test_board_zones.py   (no network, no JVM)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import board  # noqa: E402

P1 = "Ai(1)-Wilhelt Zombies B3"
P2 = "Ai(2)-Atraxa Counters B3"


def _z(turn, card, cid, frm, to, player, **extra):
    rec = {"turn": turn, "card": card, "cardId": cid, "from": frm, "to": to,
           "fromPlayer": player if frm != "None" else "",
           "toPlayer": player if to != "None" else ""}
    rec.update(extra)
    return rec


def _game(zones):
    return {"players": [P1, P2], "turns": [], "zones": zones}


def test_token_creation_is_seen_and_typed_without_scryfall():
    # "Zombie Token" is not a Scryfall card, so name-based typing can never
    # answer for it. The shim's own type data has to.
    g = _game([
        _z(3, "Zombie Token", 401, "None", "Battlefield", P1,
           types="Creature", pt="2/2", token=True),
    ])
    b, _ = board.reconstruct_from_zones(g, fetch=False)
    snap = b.snapshot()
    assert len(snap[P1]) == 1, snap
    card = snap[P1][0]
    assert card["name"] == "Zombie Token", card
    assert card["kind"] == "token", card
    assert card["pt"] == "2/2", card
    assert "assumed" not in card, card
    assert b.assumed_entries == 0, b.assumed_entries
    print("  token creation seen, typed, and carries P/T: OK")


def test_pt_is_as_of_the_move_not_the_printed_value():
    # An anthem-grown token enters as 3/3. Printed-card data would say 2/2 and
    # there is no printed card at all, which is the whole point.
    g = _game([
        _z(7, "Zombie Token", 402, "None", "Battlefield", P1,
           types="Creature", pt="3/3", token=True),
    ])
    b, _ = board.reconstruct_from_zones(g, fetch=False)
    assert b.snapshot()[P1][0]["pt"] == "3/3"
    print("  P/T recorded as of the move: OK")


def test_exits_are_exact_so_nothing_is_orphaned():
    g = _game([
        _z(1, "Sol Ring", 10, "Stack", "Battlefield", P1, types="Artifact", pt="", token=False),
        _z(2, "Zombie Token", 401, "None", "Battlefield", P1, types="Creature", pt="2/2", token=True),
        _z(2, "Zombie Token", 401, "Battlefield", "Graveyard", P1, types="Creature", pt="2/2", token=True),
        _z(3, "Sol Ring", 10, "Battlefield", "Graveyard", P1, types="Artifact", pt="", token=False),
    ])
    b, _ = board.reconstruct_from_zones(g, fetch=False)
    assert b.orphan_exits == [], b.orphan_exits
    assert b.snapshot()[P1] == [], b.snapshot()
    rep = board.validate({"games": [g]}, fetch=False)
    assert rep["basis"] == "zone_stream", rep["basis"]
    assert rep["exit_match_rate"] == 1.0, rep
    assert rep["assumed_share"] == 0.0, rep
    # The token created and destroyed in one turn — the exact object the stdout
    # path cannot see at all — is counted as a real entry here.
    assert rep["entries_total"] == 2, rep
    print("  exits match exactly, incl. a token created and killed same turn: OK")


def test_ownership_follows_the_destination_player():
    g = _game([
        _z(1, "Llanowar Elves", 20, "Hand", "Battlefield", P1, types="Creature", pt="1/1", token=False),
        _z(2, "Birds of Paradise", 21, "Hand", "Battlefield", P2, types="Creature", pt="0/1", token=False),
    ])
    b, _ = board.reconstruct_from_zones(g, fetch=False)
    snap = b.snapshot()
    assert [c["name"] for c in snap[P1]] == ["Llanowar Elves"], snap
    assert [c["name"] for c in snap[P2]] == ["Birds of Paradise"], snap
    print("  membership attributed to the destination player: OK")


def test_snapshots_are_per_turn():
    g = _game([
        _z(1, "Forest", 1, "Hand", "Battlefield", P1, types="Land", pt="", token=False),
        _z(2, "Island", 2, "Hand", "Battlefield", P1, types="Land", pt="", token=False),
        _z(3, "Swamp", 3, "Hand", "Battlefield", P1, types="Land", pt="", token=False),
    ])
    _, snaps = board.reconstruct_from_zones(g, fetch=False)
    assert [s["turn"] for s in snaps] == [1, 2, 3], snaps
    assert [len(s["board"][P1]) for s in snaps] == [1, 2, 3], snaps
    print("  one snapshot per turn, growing: OK")


def test_types_map_to_the_same_groups_as_scryfall_typing():
    g = _game([
        _z(1, "Forest", 1, "Hand", "Battlefield", P1, types="Land", pt="", token=False),
        _z(1, "Mox Amber", 2, "Stack", "Battlefield", P1, types="Artifact", pt="", token=False),
        # An artifact creature files under creature, exactly as a Scryfall type
        # line would put it.
        _z(1, "Solemn Simulacrum", 3, "Stack", "Battlefield", P1,
           types="Artifact,Creature", pt="2/2", token=False),
        _z(1, "Atraxa", 4, "Stack", "Battlefield", P1, types="Creature", pt="4/4", token=False),
        _z(1, "The Great Henge", 5, "Stack", "Battlefield", P1, types="Enchantment", pt="", token=False),
    ])
    b, _ = board.reconstruct_from_zones(g, fetch=False)
    kinds = {c["name"]: c["kind"] for c in b.snapshot()[P1]}
    assert kinds == {"Forest": "land", "Mox Amber": "artifact",
                     "Solemn Simulacrum": "creature", "Atraxa": "creature",
                     "The Great Henge": "artifact"}, kinds
    print("  core types map to the board's coarse groups: OK")


def test_pre_0_3_0_records_still_work_offline():
    # Logs written before the shim stamped types: no crash, membership still
    # exact, typing degrades to the Scryfall path (offline here, so unknown).
    g = _game([
        _z(1, "Sol Ring", 10, "Stack", "Battlefield", P1),
        _z(2, "Sol Ring", 10, "Battlefield", "Graveyard", P1),
    ])
    b, _ = board.reconstruct_from_zones(g, fetch=False)
    assert b.orphan_exits == [], b.orphan_exits
    assert b.entries == 1, b.entries
    print("  shim logs without type data degrade instead of failing: OK")


def test_stdout_only_games_still_take_the_inference_path():
    g = {"players": [P1, P2], "turns": [
        {"turn": 1, "events": [
            {"seq": 1, "action": "land_drop", "raw": f"{P1} played Forest (1)"}]},
    ]}
    assert not board.has_zone_stream(g)
    rep = board.validate({"games": [g]}, fetch=False)
    assert rep["basis"] == "inferred", rep["basis"]
    b, _ = board.build(g, fetch=False)
    assert [c["name"] for c in b.snapshot()[P1]] == ["Forest"]
    print("  stdout-only runs still reconstruct by inference: OK")


def test_mixed_result_files_are_labelled_mixed():
    zoned = _game([_z(1, "Forest", 1, "Hand", "Battlefield", P1,
                      types="Land", pt="", token=False)])
    plain = {"players": [P1, P2], "turns": []}
    rep = board.validate({"games": [zoned, plain]}, fetch=False)
    assert rep["basis"] == "mixed (1/2 zone_stream)", rep["basis"]
    assert [g["basis"] for g in rep["per_game"]] == ["zone_stream", "inferred"]
    print("  a file mixing both paths says so: OK")


def main() -> None:
    for fn in (test_token_creation_is_seen_and_typed_without_scryfall,
               test_pt_is_as_of_the_move_not_the_printed_value,
               test_exits_are_exact_so_nothing_is_orphaned,
               test_ownership_follows_the_destination_player,
               test_snapshots_are_per_turn,
               test_types_map_to_the_same_groups_as_scryfall_typing,
               test_pre_0_3_0_records_still_work_offline,
               test_stdout_only_games_still_take_the_inference_path,
               test_mixed_result_files_are_labelled_mixed):
        fn()
    print("board zone stream: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
