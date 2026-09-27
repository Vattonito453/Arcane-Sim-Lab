#!/usr/bin/env python3
"""combo_bands v0: which Spellbook variants can win (repair plan WS5 T1 item 6).

Every feature string and card list below is copied from real Commander
Spellbook records in engine/combo_cache.json, so the classifier is pinned to
the spelling Spellbook actually uses. No network, no cache read, no Forge.

Run: py engine/tests/test_combo_bands.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import combo_bands as cb  # noqa: E402


def v(cards: list[str], produces: list[str]) -> dict:
    return {"cards": cards, "produces": produces}


# Real variants (combo_cache.json).
HULLBREAKER_SOL_RING = v(["Hullbreaker Horror", "Sol Ring"],
                         ["Infinite colorless mana", "Infinite storm count"])
ORACLE_CONSULT = v(["Demonic Consultation", "Thassa's Oracle"],
                   ["Exile your library", "Win the game"])
TAINTED_PACT = v(["Tainted Pact", "Thassa's Oracle"], ["Win the game"])
KRENKO = v(["Krenko, Mob Boss", "Skirk Prospector", "Goblin Warchief"],
           ["Infinite commander casts", "Infinite creature tokens with haste",
            "Infinite death triggers", "Infinite creature ETB"])
COMBAT_PHASES = v(["Aggravated Assault", "Bear Umbra"], ["Infinite combat phases"])
KIKI = v(["Combat Celebrant", "Kiki-Jiki, Mirror Breaker"],
         ["Infinite combat phases", "Infinite creature tokens with haste",
          "Infinite creature ETB"])
MAGDA_CLOCK_TORQUE = v(["Magda, Brazen Outlaw", "Clock of Omens", "Liquimetal Torque"],
                       ["Infinite artifact ETB", "Infinite artifact tokens",
                        "Infinite tapped Treasure tokens",
                        "Put all artifact cards and a subset of creature cards from "
                        "your library onto the battlefield"])
SCEPTER_CLOCK = v(["Magistrate's Scepter", "Clock of Omens"], ["Infinite turns", "Lock"])
UMBRAL_DRUID = v(["Umbral Mantle", "Circle of Dreams Druid"],
                 ["Infinite green mana", "Infinitely large creature until end of turn",
                  "Infinite untap of creatures you control",
                  "Infinite mana creatures you control can produce"])
BIRGI = v(["Birgi, God of Storytelling // Harnfel, Horn of Bounty", "Seething Song",
           "Reiterate"], ["Infinite magecraft triggers", "Infinite storm count"])
SCURRY_OAK = v(["Scurry Oak", "Ivy Lane Denizen"],
               ["Infinite +1/+1 counters on a creature", "Infinite creature tokens",
                "Infinite creature ETB"])


def main() -> None:
    # --- single features -------------------------------------------------
    finishers = [
        "Win the game", "Win the game at the beginning of your next upkeep",
        "Each opponent loses the game", "Target opponent loses the game",
        "Target player loses the game",
        "Infinite damage", "Near-infinite damage", "Near-infinite damage to one opponent",
        "Near-infinite damage to target player", "Infinite combat damage",
        "Infinite lifeloss", "Infinite lifeloss for target opponent",
        "Near-infinite lifeloss for up to two target opponents",
        "Infinite mill", "Near-infinite mill", "Infinite mill for target opponent",
        "Exile each opponent's library", "Exile target opponent's library",
        "Infinite combat phases", "Near-infinite combat phases",
        "Infinite creature tokens with haste", "Near-infinite creature tokens with haste",
        "Infinite copies of creatures you control with haste",
        "Infinite +1/+1 counters on a creature token with haste",
        "Infinitely large creature until end of turn",
        "Infinitely powerful creatures you control until end of turn",
        "Infinite power for any creature",
        "Infinite creature tokens that are infinitely large",
    ]
    for f in finishers:
        assert cb.feature_band(f) == "finisher", (f, cb.feature_band(f))
    print(f"  {len(finishers)} win features read as finisher: OK")

    engines = [
        "Infinite colorless mana", "Infinite storm count", "Infinite colored mana",
        "Infinite ETB", "Infinite creature LTB", "Infinite untap of lands you control",
        "Infinite card draw", "Infinite draw triggers", "Infinite magecraft triggers",
        "Infinite death triggers", "Infinite lifegain", "Infinite creature tokens",
        "Infinite Treasure tokens", "Infinite self-mill", "Infinite blinking",
        "Infinite commander casts", "Infinite proliferate", "Exile your library",
        "Infinite +1/+1 counters on a creature", "Near-infinite +1/+1 counters",
        "Put all artifact cards and a subset of creature cards from your library "
        "onto the battlefield",
        "Infnite untap of legendary permanents",   # Spellbook's own typo
    ]
    for f in engines:
        assert cb.feature_band(f) == "engine", (f, cb.feature_band(f))
    print(f"  {len(engines)} resource features read as engine: OK")

    for f in ("Lock", "Infinite turns", "Near-infinite turns", "Mass Land Denial",
              "Opponents can't cast spells", "Players skip their untap steps",
              "You control one opponent on each of their turns"):
        assert cb.feature_band(f) == "lock", (f, cb.feature_band(f))
    print("  lock features read as lock: OK")

    # Never a win: a draw, damage or life loss that also hits the pilot,
    # creature-only damage, board wipes, protection, and a feature v0 has
    # never seen.
    for f in ("Draw the game", "Near-infinite damage to all players",
              "Near-infinite lifeloss for all players", "Infinite damage to creatures",
              "Near-infinite damage to creatures", "Destroy all creatures opponents control",
              "Each opponent's life total becomes 1", "You have protection from everything",
              "Infinite -1/-1 counters on creatures opponents control",
              "Your opponents mill cards instead of drawing them",
              "Some feature Spellbook adds next year", ""):
        assert cb.feature_band(f) != "finisher", (f, cb.feature_band(f))
    assert cb.feature_band("Draw the game") == "other"
    assert cb.feature_band("Some feature Spellbook adds next year") == "other"
    print("  draws, self-hitting loops, wipes and unknown features never read as finisher: OK")

    # --- variants ---------------------------------------------------------
    assert cb.band(HULLBREAKER_SOL_RING) == "engine"
    assert not cb.is_win_band(HULLBREAKER_SOL_RING)
    print("  Hullbreaker Horror + Sol Ring = engine: OK")

    c = cb.classify(ORACLE_CONSULT)
    assert c["band"] == "finisher" and c["basis"] == ["Win the game"], c
    assert c["pieces"] == 2 and c["version"] == 0, c
    assert cb.is_win_band(ORACLE_CONSULT) and cb.is_win_band(TAINTED_PACT)
    print("  Thassa's Oracle + Demonic Consultation = finisher (basis: Win the game): OK")

    assert cb.is_win_band(KRENKO), cb.classify(KRENKO)
    assert cb.classify(KRENKO)["basis"] == ["Infinite creature tokens with haste"]
    print("  infinite hasty tokens = finisher: OK")

    assert cb.is_win_band(COMBAT_PHASES) and cb.is_win_band(KIKI)
    print("  infinite combat phases = finisher: OK")

    assert cb.is_win_band(UMBRAL_DRUID), cb.classify(UMBRAL_DRUID)
    print("  infinitely large creature = finisher: OK")

    assert cb.band(MAGDA_CLOCK_TORQUE) == "engine", cb.classify(MAGDA_CLOCK_TORQUE)
    print("  Magda + Clock of Omens + Liquimetal Torque = engine (no win feature): OK")

    assert cb.band(SCEPTER_CLOCK) == "lock" and not cb.is_win_band(SCEPTER_CLOCK)
    print("  Magistrate's Scepter + Clock of Omens = lock, not a win: OK")

    assert cb.band(BIRGI) == "engine" and cb.band(SCURRY_OAK) == "engine"
    print("  storm/magecraft and +1/+1 counter loops = engine: OK")

    # A variant is "engine" only when EVERY feature is a resource.
    mixed = v(["A", "B"], ["Infinite colored mana", "Destroy all creatures opponents control"])
    assert cb.band(mixed) == "other" and not cb.is_win_band(mixed)
    # Finisher beats lock beats engine.
    assert cb.band(v(["A", "B"], ["Lock", "Infinite colored mana"])) == "lock"
    assert cb.band(v(["A", "B"], ["Lock", "Infinite damage"])) == "finisher"
    print("  band precedence (finisher > lock > engine only if all resources): OK")

    # Card count: no pieces is no line; one piece that wins still wins.
    assert cb.band(v([], ["Win the game"])) == "other"
    assert cb.band(v(["Solo Card"], ["Win the game"])) == "finisher"
    assert cb.band(v(["A", "B"], [])) == "other"
    assert cb.band({}) == "other" and cb.band(None) == "other"
    print("  degenerate variants (no pieces, no features) are never a win: OK")

    # The raw Spellbook record shape reads the same as the slim one.
    raw = {"uses": [{"card": {"name": "Demonic Consultation"}},
                    {"card": {"name": "Thassa's Oracle"}}],
           "produces": [{"feature": {"name": "Exile your library"}},
                        {"feature": {"name": "Win the game"}}]}
    assert cb.classify(raw)["band"] == "finisher" and cb.classify(raw)["pieces"] == 2
    print("  raw Spellbook records classify like slim ones: OK")

    assert set(cb.BANDS) == {"finisher", "lock", "engine", "other"}
    assert cb.WIN_BANDS == frozenset({"finisher"})
    print("combo_bands v0: ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
