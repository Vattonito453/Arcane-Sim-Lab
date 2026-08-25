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
}


def fake_get_many(names, fetch=False):
    return {cards.key(n): f for n, f in FACTS.items()}


def write_dck(tmp: Path) -> Path:
    p = tmp / "toy.dck"
    lines = ["[metadata]", "Name=toy", "[Commander]", "1 Commander Cat", "[Main]"]
    for n in FACTS:
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
