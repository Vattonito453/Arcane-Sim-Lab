#!/usr/bin/env python3
"""Rule-based deck archetype classification, with stock-AI win-rate baselines.

The baselines live HERE and nowhere else in code — they come from the Bias 2
table in engine/SIM_CALIBRATION.md (seat-fair measurement across 320+
deck-games, July 2026, stock Forge AI). Import BASELINES; never restate the
numbers. If SIM_CALIBRATION.md is re-measured (e.g. under the humanized
agent), update the table there and the dict here in the same commit.

Classification is deliberately simple and rule-based, and it must explain
itself: the `why` string is shown to the user and fed to the coaching LLM,
so it states the counts the decision was made from. "unknown" is a valid
answer — a class this module cannot justify is not forced.

Thresholds (measured against the four fixture decks — see
tests/test_archetype.py):
    voltron:  >= 10 Equipment/Aura cards, or the voltron-commander-damage
              tag marks >= 45% of nonland cards
    politics: >= 5 cards with vote/goad/monarch/tempting-offer text
    engine:   an engine tag (counters-proliferate, spellslinger-burn,
              stax-control, mill) marks >= 33% of nonland cards — checked
              BEFORE the creature rule, because engine decks can carry many
              creatures (Kilo runs 27) and still live or die by the engine
    creature: creatures are >= 40% of nonland cards
    unknown:  nothing above holds, or >25% of the list has no cached facts

Usage:
  python3 archetype.py <deck.dck> [more.dck ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cards  # noqa: E402
from deck_plan import TAG_MARKERS, read_dck  # noqa: E402

# engine/SIM_CALIBRATION.md, Bias 2: creature-forward 38%, engine/spell 12%.
# Voltron is listed inside the creature-forward class there, so it shares the
# 38% baseline — but its sim result is a floor (calibration rule 4). Politics
# has no measured baseline; the AI cannot pilot it at all.
BASELINES: dict[str, float | None] = {
    "creature": 0.38,
    "voltron": 0.38,
    "engine": 0.12,
    "politics": None,
    "unknown": None,
}

# Classes whose sim win rate is a floor, not a verdict (SIM_CALIBRATION rule 4).
SIM_FLOOR_CLASSES = {"voltron", "politics"}

ENGINE_TAGS = ("counters-proliferate", "spellslinger-burn", "stax-control", "mill")

_EQUIP_AURA = re.compile(r"\bEquipment\b|\bAura\b")
_POLITICS = re.compile(r"\bvote\b|\bgoad\b|monarch|tempting offer", re.I)

VOLTRON_SUITE_MIN = 10
VOLTRON_TAG_SHARE = 0.45
POLITICS_CARDS_MIN = 5
ENGINE_TAG_SHARE = 1 / 3
CREATURE_SHARE = 0.40
UNKNOWN_FACTS_SHARE = 0.25


def classify(decklist: list[str], commander: str | None = None,
             fetch: bool = False) -> dict:
    """Classify a decklist into an archetype with baseline and rationale.

    `decklist` is the main deck's card names; `commander` is counted with it
    for signals. Card facts come from the Scryfall disk cache (fetch=False by
    default — classification must never surprise-hit the network).
    """
    names = list(dict.fromkeys(
        ([commander] if commander else []) + list(decklist)))
    facts = cards.get_many(names, fetch=fetch)

    def fact(n: str) -> dict:
        return facts.get(cards.key(n)) or facts.get(n) or {}

    missing = [n for n in names if not fact(n)]
    if names and len(missing) / len(names) > UNKNOWN_FACTS_SHARE:
        return {
            "class": "unknown",
            "baseline": BASELINES["unknown"],
            "sim_is_floor": False,
            "why": (f"{len(missing)} of {len(names)} cards have no cached "
                    f"Scryfall facts, which is too many to classify from"),
        }

    nonland: list[str] = []
    creatures: list[str] = []
    equip_aura: list[str] = []
    politics: list[str] = []
    for n in names:
        f = fact(n)
        tline = f.get("type_line") or ""
        text = f.get("oracle_text") or ""
        if "Land" in tline and "Creature" not in tline:
            continue
        nonland.append(n)
        if "Creature" in tline:
            creatures.append(n)
        if _EQUIP_AURA.search(tline):
            equip_aura.append(n)
        if _POLITICS.search(text):
            politics.append(n)

    if not nonland:
        return {"class": "unknown", "baseline": None, "sim_is_floor": False,
                "why": "no nonland cards recognised"}

    tag_counts = {
        tag: sum(1 for n in nonland
                 if any(m in (fact(n).get("oracle_text") or "").lower()
                        for m in markers))
        for tag, markers in TAG_MARKERS.items()
    }
    total = len(nonland)
    voltron_share = tag_counts.get("voltron-commander-damage", 0) / total
    engine_tag, engine_count = max(
        ((t, tag_counts.get(t, 0)) for t in ENGINE_TAGS), key=lambda kv: kv[1])
    creature_share = len(creatures) / total

    def result(cls: str, why: str) -> dict:
        return {"class": cls, "baseline": BASELINES[cls],
                "sim_is_floor": cls in SIM_FLOOR_CLASSES, "why": why}

    if len(equip_aura) >= VOLTRON_SUITE_MIN or voltron_share >= VOLTRON_TAG_SHARE:
        return result("voltron", (
            f"{len(equip_aura)} Equipment/Aura cards and "
            f"{tag_counts.get('voltron-commander-damage', 0)} of {total} nonland "
            f"cards carry voltron text: a commander-damage deck. The AI cannot "
            f"time protection, so simulated results are a floor"))
    if len(politics) >= POLITICS_CARDS_MIN:
        return result("politics", (
            f"{len(politics)} of {total} nonland cards vote, goad, or pass the "
            f"monarch: a politics deck. The AI cannot pilot table politics, so "
            f"simulated results are a floor"))
    if engine_count / total >= ENGINE_TAG_SHARE:
        return result("engine", (
            f"{engine_count} of {total} nonland cards support the {engine_tag} "
            f"engine ({len(creatures)} creatures do not change the plan): an "
            f"engine deck, read against the 12% stock-AI class average"))
    if creature_share >= CREATURE_SHARE:
        return result("creature", (
            f"{len(creatures)} of {total} nonland cards are creatures "
            f"({creature_share:.0%}): a creature-forward deck, read against "
            f"the 38% class average"))
    return result("unknown", (
        f"no signal is decisive: {len(creatures)}/{total} creatures, "
        f"top engine tag {engine_tag} at {engine_count}/{total}, "
        f"{len(equip_aura)} Equipment/Auras, {len(politics)} politics cards"))


def classify_dck(path: str | Path, fetch: bool = False) -> dict:
    """Convenience wrapper: classify a .dck file by path."""
    _, commanders, main = read_dck(path)
    out = classify(main, commanders[0] if commanders else None, fetch=fetch)
    out["deck"] = Path(path).name
    out["commander"] = commanders[0] if commanders else None
    return out


def main() -> None:
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not paths:
        sys.exit("usage: python3 archetype.py <deck.dck> [more.dck ...]")
    for p in paths:
        print(json.dumps(classify_dck(p), indent=2))


if __name__ == "__main__":
    main()
