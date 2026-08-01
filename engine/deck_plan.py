#!/usr/bin/env python3
"""Build a deck's play plan — the strategy data the sim agent runs on.

The plan is the bridge in task 07's architecture: all card knowledge stays
here (our side of the GPL boundary) and crosses to simlab-forge-shim as
JSON. Oracle text is used for *strategy hints only* — Forge remains the sole
adjudicator of what happens in a game (CLAUDE.md invariant).

Sources: win-condition tag heuristics over oracle text (user-editable at
import later — task 07), card roles, and combo lines from combos.py's disk
cache when available.

Usage:
  python3 deck_plan.py <deck.dck> [more.dck ...] [--out plans.json] [--fetch]

Zero dependencies (stdlib + sibling modules).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cards  # noqa: E402
import combos  # noqa: E402

# Win-condition tag vocabulary. Each tag lists lowercase oracle-text markers;
# a card "supports" a tag when any marker appears. Extend freely — the same
# vocabulary should eventually drive deck_telemetry watches.
TAG_MARKERS: dict[str, list[str]] = {
    "counters-proliferate": ["proliferate", "charge counter", "+1/+1 counter",
                             "poison counter", "energy counter", "loyalty counter"],
    "go-wide-tokens": ["create a", "token", "populate", "for each creature you control"],
    "voltron-commander-damage": ["equip", "attach", "enchanted creature gets",
                                 "double strike", "equipped creature"],
    "aristocrats-drain": ["sacrifice a creature", "whenever a creature you control dies",
                          "each opponent loses"],
    "spellslinger-burn": ["instant or sorcery", "copy target", "deals damage to any target",
                          "whenever you cast a noncreature spell"],
    "mill": ["mills", "mill ", "puts the top", "from the top of their library into"],
    "stax-control": ["players can't", "spells cost {1} more", "doesn't untap",
                     "counter target"],
    "tribal-anthem": ["other ", "you control get +", "creatures you control get +"],
    "ramp-big-mana": ["search your library for a land", "add one mana", "add {c}{c}",
                      "add two mana", "lands you control"],
    "reanimator": ["return target creature card from your graveyard",
                   "from your graveyard to the battlefield"],
    "lifegain": ["you gain", "whenever you gain life"],
}

# Personality defaults per dominant tag; everything is a starting point the
# import UI can expose later. Stage 4 dials: grudgeWeight scales how much
# being attacked raises a seat's threat in my eyes; kingmakerRatio is the
# leader/weakest threat ratio past which attacks re-aim off the weakest seat;
# politics raises the counterspell bar while another opponent holds open
# mana; triggerMiss is the decline chance for OPTIONAL triggers only
# (mandatory triggers can never be missed — that would be an illegal game).
TAG_PERSONALITY: dict[str, dict] = {
    "go-wide-tokens": {"aggression": 0.7, "splitAttacks": 0.85, "blockiness": 0.5,
                       "counterThreshold": 6, "dangerLife": 8,
                       "grudgeWeight": 0.25, "kingmakerRatio": 1.6,
                       "politics": 0.4, "triggerMiss": 0.04},
    "voltron-commander-damage": {"aggression": 0.8, "splitAttacks": 0.4, "blockiness": 0.4,
                                 "counterThreshold": 6, "dangerLife": 8,
                                 "grudgeWeight": 0.3, "kingmakerRatio": 1.4,
                                 "politics": 0.3, "triggerMiss": 0.04},
    "spellslinger-burn": {"aggression": 0.6, "splitAttacks": 0.7, "blockiness": 0.5,
                          "counterThreshold": 4, "dangerLife": 10,
                          "grudgeWeight": 0.2, "kingmakerRatio": 1.6,
                          "politics": 0.6, "triggerMiss": 0.03},
    "stax-control": {"aggression": 0.35, "splitAttacks": 0.6, "blockiness": 0.75,
                     "counterThreshold": 4, "dangerLife": 12,
                     "grudgeWeight": 0.15, "kingmakerRatio": 1.8,
                     "politics": 0.8, "triggerMiss": 0.02},
    "mill": {"aggression": 0.35, "splitAttacks": 0.6, "blockiness": 0.75,
             "counterThreshold": 4, "dangerLife": 12,
             "grudgeWeight": 0.15, "kingmakerRatio": 1.8,
             "politics": 0.8, "triggerMiss": 0.02},
    "_default": {"aggression": 0.55, "splitAttacks": 0.7, "blockiness": 0.6,
                 "counterThreshold": 5, "dangerLife": 8,
                 "grudgeWeight": 0.2, "kingmakerRatio": 1.6,
                 "politics": 0.5, "triggerMiss": 0.03},
}

_REMOVAL = re.compile(r"destroy target|exile target|deals \d+ damage to target creature",
                      re.I)
_PROTECTION = re.compile(r"hexproof|indestructible|protection from|counter target spell|"
                         r"can't be countered|phase(s)? out", re.I)
_FINISHER = re.compile(r"wins? the game|loses? the game|combat damage to a player|"
                       r"infect|damage can't be prevented", re.I)


def read_dck(path: str | Path) -> tuple[str, list[str], list[str]]:
    """Return (deck name, commander names, main names)."""
    name = Path(path).stem
    commanders: list[str] = []
    main: list[str] = []
    section = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if section == "metadata":
            if line.lower().startswith("name="):
                name = line.split("=", 1)[1].strip()
            continue
        m = re.match(r"(\d+)\s+(.+?)(?:\|.*)?$", line)
        if not m:
            continue
        card = m.group(2).strip()
        if section == "commander":
            commanders.append(card)
        elif section in ("main", "avatar", None):
            if section == "main":
                main.append(card)
    return name, commanders, main


def build_plan(path: str | Path, fetch: bool = False) -> tuple[str, dict]:
    deck_name, commanders, main = read_dck(path)
    names = commanders + main
    facts = cards.get_many(names, fetch=fetch)

    # Tag scoring: how many cards support each tag.
    tag_hits: dict[str, list[str]] = {t: [] for t in TAG_MARKERS}
    for n in names:
        f = facts.get(cards.key(n)) or facts.get(n) or {}
        text = (f.get("oracle_text") or "").lower()
        tline = (f.get("type_line") or "").lower()
        if "land" in tline and "creature" not in tline:
            continue
        for tag, markers in TAG_MARKERS.items():
            if any(m in text for m in markers):
                tag_hits[tag].append(n)
    ranked = sorted(tag_hits.items(), key=lambda kv: -len(kv[1]))
    tags = [t for t, hits in ranked[:2] if len(hits) >= 5]
    if not tags and ranked[0][1]:
        tags = [ranked[0][0]]
    tag_cards = {n for t in tags for n in tag_hits[t]}

    # Combo lines from the Spellbook disk cache (offline unless --fetch).
    combo_pieces: set[str] = set()
    try:
        combo = combos.combos_for_dck(path, fetch=fetch)
        for v in (combo or {}).get("combos", []):
            combo_pieces.update(v.get("cards", []))
    except Exception:
        pass  # no cache and no network — plans work without combos

    weights: dict[str, int] = {}
    roles: dict[str, str] = {}
    for n in names:
        f = facts.get(cards.key(n)) or facts.get(n) or {}
        text = f.get("oracle_text") or ""
        tline = f.get("type_line") or ""
        cmc = f.get("cmc") or 0
        if "Land" in tline and "Creature" not in tline:
            roles[n] = "land"
            continue
        if n in combo_pieces:
            roles[n], weights[n] = "combo-piece", 8
        elif n in tag_cards and (_FINISHER.search(text) or cmc >= 4):
            roles[n], weights[n] = "payoff", 8
        elif n in tag_cards:
            roles[n], weights[n] = "enabler", 5
        elif _PROTECTION.search(text):
            roles[n], weights[n] = "protection", 4
        elif _REMOVAL.search(text):
            roles[n], weights[n] = "removal", 3
        else:
            roles[n], weights[n] = "filler", 1
    for c in commanders:
        weights[c] = max(weights.get(c, 0), 8)
        roles[c] = "commander"

    keep = sorted((n for n, w in weights.items() if w >= 5),
                  key=lambda n: -weights[n])[:16]
    threat = sorted((n for n, w in weights.items() if w >= 7), key=lambda n: -weights[n])
    personality = dict(TAG_PERSONALITY.get(tags[0] if tags else "_default",
                                           TAG_PERSONALITY["_default"]))

    plan = {
        "tags": tags,
        "mulligan": {"minLands": 2, "maxLands": 5, "maxMulls": 2, "keepCards": keep},
        "weights": {n: w for n, w in weights.items() if w > 1},
        "threat": threat,
        "roles": roles,           # for the UI / coaching; the shim ignores it
        "personality": personality,
    }
    return deck_name, plan


def build_plans(paths: list[str | Path], fetch: bool = False) -> dict:
    decks = {}
    for p in paths:
        name, plan = build_plan(p, fetch=fetch)
        decks[name] = plan
    return {"decks": decks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("decks", nargs="+", help=".dck files")
    ap.add_argument("--out", default=None, help="write plans JSON here (default stdout)")
    ap.add_argument("--fetch", action="store_true",
                    help="allow Scryfall/Spellbook network fetches (cache-only otherwise)")
    args = ap.parse_args()
    plans = build_plans(args.decks, fetch=args.fetch)
    payload = json.dumps(plans, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        for name, plan in plans["decks"].items():
            print(f"{name}: tags={plan['tags']} keeps={len(plan['mulligan']['keepCards'])} "
                  f"threat={len(plan['threat'])}")
        print(f"wrote {args.out}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
