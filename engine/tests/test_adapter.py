#!/usr/bin/env python3
"""Unit test for forge_log_adapter using a synthetic log in Forge's exact
`Caption: message` format (captions verified against GameLogEntryType in
Forge 2.0.13 source). Run: python3 tests/test_adapter.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from forge_log_adapter import parse_forge_log  # noqa: E402

SAMPLE = """
Simulation mode
Game 1 of 2
Mulligan: Alice has kept a hand of 7 cards
Mulligan: Bob has mulliganed down to 6 cards
Turn: Turn 1 (Alice)
Turn: Turn 1 (Ai(9)-Nested Parens Deck)
Phase: Alice's Upkeep
Land: Alice played Mountain
Phase: Alice's Main 1
Add To Stack: Alice cast Sol Ring
Resolve Stack: Sol Ring
Turn: Turn 1 (Bob)
Land: Bob played Swamp
Turn: Turn 2 (Alice)
Land: Alice played Mountain
Add To Stack: Alice cast Krenko, Mob Boss
Resolve Stack: Krenko, Mob Boss
Phase: Alice's Combat
Combat: Alice assigned Krenko, Mob Boss to attack Bob
Damage: Krenko, Mob Boss deals 3 combat damage to Bob.
Life: Bob has 37 life
Zone Change: Doom Blade moves from Hand to Graveyard
Game Outcome: Alice has won because all opponents have lost
Match Result: Alice: 1 Bob: 0

Game Result: Game 1 ended in 8123 ms. Alice has won!

Turn: Turn 1 (Bob)
Land: Bob played Swamp
Game Result: Game 2 ended in a Draw
"""


def main() -> None:
    r = parse_forge_log(SAMPLE, source="unit-test")
    games = r["games"]
    assert len(games) == 2, f"expected 2 games, got {len(games)}"

    g1 = games[0]
    assert g1["result"]["winner"] == "Alice", g1["result"]
    assert g1["result"]["duration_ms"] == 8123
    assert [t["turn"] for t in g1["turns"]] == [1, 1, 1, 2]
    assert g1["turns"][0]["active_player"] == "Alice"
    assert g1["turns"][1]["active_player"] == "Ai(9)-Nested Parens Deck"  # nested parens survive
    assert set(g1["players"]) == {"Alice", "Ai(9)-Nested Parens Deck", "Bob"}

    # pregame mulligans captured before any Turn line
    assert [e["action"] for e in g1["events_pregame"]] == ["mulligan", "mulligan"]

    t2 = g1["turns"][3]
    actions = [e["action"] for e in t2["events"]]
    assert "land_drop" in actions and "stack_add" in actions and "combat" in actions

    dmg = next(e for e in t2["events"] if e["action"] == "damage")
    assert dmg["amount"] == 3 and dmg["target"] == "Bob", dmg
    life = next(e for e in t2["events"] if e["action"] == "life_change")
    assert life["player"] == "Bob" and life["life"] == 37, life

    g2 = games[1]
    assert g2["result"]["draw"] is True

    # Every seat that took a turn appears, winless seats at 0 — consumers read
    # the pod roster off these keys to compute the even-seats baseline.
    s = r["summary"]
    assert s == {
        "games": 2,
        "draws": 1,
        "wins": {"Alice": 1, "Ai(9)-Nested Parens Deck": 0, "Bob": 0},
        "win_rates": {"Alice": 0.5, "Ai(9)-Nested Parens Deck": 0.0, "Bob": 0.0},
    }, s

    print("forge_log_adapter: ALL ASSERTIONS PASSED")
    print(f"  games={s['games']} draws={s['draws']} wins={s['wins']}")


if __name__ == "__main__":
    main()
