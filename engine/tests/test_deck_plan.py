#!/usr/bin/env python3
"""deck_plan search targets + tutor promotion (task 20 Stage 1).

Synthetic card facts throughout: no cache, no network, no Forge.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import cards  # noqa: E402
import deck_plan  # noqa: E402

FACTS = {
    "Commander Cat": {"oracle_text": "Flying", "type_line": "Legendary Creature — Cat", "cmc": 3},
    "Big Portal": {"oracle_text": "Each opponent sacrifices three creatures.",
                   "type_line": "Artifact", "cmc": 9},
    "Win Button": {"oracle_text": "You win the game.", "type_line": "Enchantment", "cmc": 5},
    "Mana Rock": {"oracle_text": "{T}: Add {C}{C}.", "type_line": "Artifact", "cmc": 1},
    "Overrun Ape": {"oracle_text": "Creatures you control get +3/+3 until end of turn.",
                    "type_line": "Creature — Ape", "cmc": 8},
    "Shield Spell": {"oracle_text": "Target creature gains hexproof.",
                     "type_line": "Instant", "cmc": 1},
    "Zap": {"oracle_text": "Destroy target artifact.", "type_line": "Instant", "cmc": 2},
    "Fetch Friend": {"oracle_text": "Search your library for a creature card.",
                     "type_line": "Sorcery", "cmc": 2},
    "Land Fetch": {"oracle_text": "Search your library for a land card.",
                   "type_line": "Sorcery", "cmc": 2},
    "Plain Bear": {"oracle_text": "", "type_line": "Creature — Bear", "cmc": 2},
    "Some Mountain": {"oracle_text": "{T}: Add {R}.", "type_line": "Basic Land — Mountain",
                      "cmc": 0},
    # A punisher engine: no power, no keep weight, hurts the table every turn.
    "Pain Box": {"oracle_text": "At the beginning of each opponent's upkeep, this artifact "
                                "deals 2 damage to that player.",
                 "type_line": "Artifact", "cmc": 3},
    # The same words on a sorcery are burn, not an engine.
    "Blast": {"oracle_text": "Blast deals 3 damage to each opponent.",
              "type_line": "Sorcery", "cmc": 4},
}

# A second toy deck for the punisher rule alone: these texts trip archetype
# tag markers (card draw, life loss) and would re-tag the main fixture.
FACTS2 = {
    "Commander Cat": FACTS["Commander Cat"],
    "Some Mountain": FACTS["Some Mountain"],
    # A punisher engine: no power, no keep weight, hurts the table every turn.
    "Pain Box": FACTS["Pain Box"],
    # The same words on a sorcery are burn, not an engine.
    "Blast": FACTS["Blast"],
    # Triggers on the table's actions without hurting anyone: a value engine,
    # not a punisher (the first regex cut listed Consecrated Sphinx).
    "Card Sphinx": {"oracle_text": "Whenever an opponent draws a card, you may draw two cards.",
                    "type_line": "Creature — Sphinx", "cmc": 6},
    # Hurts the table but on the OWNER's board events: an aristocrat payoff.
    "Blood Cutthroat": {"oracle_text": "Whenever this creature or another creature you control "
                                       "dies, each opponent loses 1 life.",
                        "type_line": "Creature — Vampire", "cmc": 2},
}


def fake_get_many(names, fetch=False):
    return {cards.key(n): f for n, f in FACTS.items()}


def write_dck(tmp: Path, facts: dict = FACTS, name: str = "toy") -> Path:
    p = tmp / f"{name}.dck"
    lines = ["[metadata]", f"Name={name}", "[Commander]", "1 Commander Cat", "[Main]"]
    for n in facts:
        if n != "Commander Cat":
            lines.append(f"1 {n}")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main() -> None:
    deck_plan.cards.get_many = fake_get_many
    deck_plan.combos.combos_for_dck = lambda p, fetch=False: {}  # no lines

    with tempfile.TemporaryDirectory() as td:
        _, plan = deck_plan.build_plan(write_dck(Path(td)))

    t = plan["search"]["targets"]
    ctx = plan["search"]["context"]

    assert plan["weights"].get("Fetch Friend") == 5 and plan["roles"]["Fetch Friend"] == "tutor", \
        "nonland tutor must earn weight 5 with NO combo lines"
    print("  tutor promoted without combo lines: OK")

    assert "Land Fetch" not in plan["tutors"], "land fetch is ramp, not a tutor"
    print("  land fetch stays a non-tutor: OK")

    assert t.get("Win Button") == 8, "finisher text ranks 8"
    assert t.get("Big Portal") == 6, "cmc>=6 bomb the tags missed ranks 6"
    assert t.get("Mana Rock") == 5 and ctx["Mana Rock"] == {"hint": "ramp", "beforeRound": 5}, \
        "cheap mana source ranks 5 gated to the early rounds"
    assert t.get("Shield Spell") == 4, "protection ranks 4"
    assert t.get("Zap") == 3, "removal ranks 3"
    print("  target scale (8/6/5/4/3): OK")

    assert t.get("Overrun Ape") == 6 and ctx["Overrun Ape"] == {"hint": "finisher",
                                                                "minCreatures": 3}, \
        "board payoff needs a board first (Finale case)"
    print("  finisher context on board payoffs: OK")

    assert "Commander Cat" not in t, "commanders live in the command zone"
    assert "Some Mountain" not in t, "lands are not search targets"
    assert "Plain Bear" not in t, "value-1 filler stays implicit"
    print("  exclusions (commander, land, filler): OK")

    assert plan["factsCoverage"] == 1.0
    print("  factsCoverage recorded: OK")

    # Threat list: punisher PERMANENTS count (shim 0.14.0 reads the list into
    # its table threat index, at 8, and that index also gates counterspells);
    # the same text on a sorcery does not, nor do value engines or aristocrats.
    assert "Pain Box" in plan["threat"], plan["threat"]
    assert "Blast" not in plan["threat"], plan["threat"]
    assert "Commander Cat" in plan["threat"], "the commander is always a threat"
    deck_plan.cards.get_many = lambda names, fetch=False: {cards.key(n): f for n, f in FACTS2.items()}
    with tempfile.TemporaryDirectory() as td:
        _, plan2 = deck_plan.build_plan(write_dck(Path(td), FACTS2, "toy2"))
    assert "Pain Box" in plan2["threat"], plan2["threat"]
    assert "Card Sphinx" not in plan2["threat"], plan2["threat"]
    assert "Blood Cutthroat" not in plan2["threat"], plan2["threat"]
    deck_plan.cards.get_many = fake_get_many
    print("  punisher permanents are threats; sorceries, value engines, aristocrats are not: OK")

    assert plan["personality"]["openThreatShare"] == 0.6, plan["personality"]
    print("  openThreatShare dial shipped in the plan: OK")
    assert plan["personality"]["holdInstants"] == 1.0, plan["personality"]
    assert plan["personality"]["holdInstantUntilRound"] == 10, plan["personality"]
    print("  holdInstants / holdInstantUntilRound dials shipped in the plan: OK")

    # Degraded facts: coverage drops and heuristics stay quiet, not wrong.
    deck_plan.cards.get_many = lambda names, fetch=False: {}
    with tempfile.TemporaryDirectory() as td:
        _, cold = deck_plan.build_plan(write_dck(Path(td)))
    assert cold["factsCoverage"] == 0.0
    assert cold["search"]["targets"] == {}, "no facts, no fabricated targets"
    print("  cold cache degrades honestly: OK")

    print("deck_plan targets: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
