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
# Stage 5 dial: greed is combo pursuit vs safety — how willing the agent is
# to jam the final piece of a line into open enemy mana instead of waiting.
# Pursuit itself only activates behind the line-of-sight gate (≤1 piece
# missing, or 2 with a tutor in hand) and never alters combat decisions.
#
# MEASURED 2026-08-25 (studies/agent_viability): four of these dials existed
# to make the agent play WORSE so it would look human, and they cost about
# 6 percentage points of win rate against stock Forge while buying nothing —
# the correlation study had already found humanization does not improve
# predictive validity. They are now set to play-to-win:
#   greed 1.0        never sit on the piece that wins the game
#   triggerMiss 0    never decline a beneficial optional trigger
#   splitAttacks 0   kill one opponent rather than spreading damage
#   politics 0       do not hold interaction because someone else has mana
# The cEDH corpus is a picture of STRONG human play, so "human-like" means
# converting, not erring. Any future proposal to re-introduce error has to
# earn it with a measured gain, not an argument about realism.
TAG_PERSONALITY: dict[str, dict] = {
    "go-wide-tokens": {"aggression": 0.7, "splitAttacks": 0.0, "blockiness": 0.5,
                       "counterThreshold": 6, "dangerLife": 8,
                       "grudgeWeight": 0.25, "kingmakerRatio": 1.6,
                       "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "voltron-commander-damage": {"aggression": 0.8, "splitAttacks": 0.0, "blockiness": 0.4,
                                 "counterThreshold": 6, "dangerLife": 8,
                                 "grudgeWeight": 0.3, "kingmakerRatio": 1.4,
                                 "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "spellslinger-burn": {"aggression": 0.6, "splitAttacks": 0.0, "blockiness": 0.5,
                          "counterThreshold": 4, "dangerLife": 10,
                          "grudgeWeight": 0.2, "kingmakerRatio": 1.6,
                          "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "stax-control": {"aggression": 0.35, "splitAttacks": 0.0, "blockiness": 0.75,
                     "counterThreshold": 4, "dangerLife": 12,
                     "grudgeWeight": 0.15, "kingmakerRatio": 1.8,
                     "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "mill": {"aggression": 0.35, "splitAttacks": 0.0, "blockiness": 0.75,
             "counterThreshold": 4, "dangerLife": 12,
             "grudgeWeight": 0.15, "kingmakerRatio": 1.8,
             "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "_default": {"aggression": 0.55, "splitAttacks": 0.0, "blockiness": 0.6,
                 "counterThreshold": 5, "dangerLife": 8,
                 "grudgeWeight": 0.2, "kingmakerRatio": 1.6,
                 "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
}

_REMOVAL = re.compile(r"destroy target|exile target|deals \d+ damage to target creature",
                      re.I)
# Nonland tutors: what the clause after "search your library for" names.
# Land-only fetch (Cultivate, fetchlands) is ramp, not a path to a combo
# piece. Type-restricted tutors (Worldly Tutor) still count — the gate is
# knowingly a little optimistic; Forge only offers legal search targets, so
# a mismatch costs nothing at choice time.
_TUTOR_CLAUSE = re.compile(r"search your librar(?:y|ies) for ([^.;\n]*)", re.I)
# Land fetch isn't tutoring: catch both the word "land" and basic type names
# ("a Forest card" — Wood Elves; "a Plains card" — plainscycling).
_LAND_CLAUSE = re.compile(r"land|plains|island|swamp|mountain|forest|gate\b", re.I)
_PROTECTION = re.compile(r"hexproof|indestructible|protection from|counter target spell|"
                         r"can't be countered|phase(s)? out", re.I)
_FINISHER = re.compile(r"wins? the game|loses? the game|combat damage to a player|"
                       r"infect|damage can't be prevented", re.I)
# Search-target heuristics (task 20 Stage 1). Same vocabulary style as the
# tag markers: cheap oracle-text tests, no new inference regime.
_MANA_SOURCE = re.compile(r"add \{|add one mana|add two mana", re.I)
_BOARD_PAYOFF = re.compile(r"creatures? you control get \+|creatures you control gain", re.I)


# Synergy lines: a deck's win condition when Commander Spellbook has nothing.
#
# Spellbook catalogues competitive and infinite combos. Queried for all 66
# Commander precons it returns ZERO variants -- not even "almost included" --
# so `lines` is empty and the shim's combo pursuit is structurally inert on
# the decks most players actually own. But a precon absolutely has a win
# condition: it is "make tokens, then anthem them", "sacrifice creatures,
# then drain", "put counters on things, then proliferate". Those are combos
# that need to fire ONCE, not infinitely.
#
# Each entry pairs an ENABLER pattern with a PAYOFF pattern for one archetype.
# Same oracle-text heuristic style as TAG_MARKERS -- no new inference regime,
# no network dependency, and Forge still adjudicates every rule.
SYNERGY_LINES: dict[str, tuple[str, str]] = {
    "go-wide-tokens": (r"create[s]? .*token", r"creatures you control get \+|"
                       r"whenever .*creature .*enters|for each creature you control"),
    "aristocrats-drain": (r"sacrifice a creature|whenever .*you control dies",
                          r"each opponent loses|drain|whenever .*dies, .*gain"),
    "counters-proliferate": (r"put .*\+1/\+1 counter|enters with .*counter",
                             r"proliferate|for each .*counter|remove .*counter"),
    "tribal-anthem": (r"create[s]? .*token|search your library for a creature",
                      r"other .*you control get \+|creatures you control get \+"),
    "lifegain": (r"you gain \d+ life|gain life", r"whenever you gain life"),
    "spellslinger-burn": (r"instant or sorcery|copy target",
                          r"whenever you cast a noncreature spell|deals damage to any target"),
    "mill": (r"mills|puts the top", r"from (a|your|their) graveyard|for each card in"),
    "reanimator": (r"discard|mills|put .*into your graveyard",
                   r"return target creature card from your graveyard"),
    "ramp-big-mana": (r"add .*mana|search your library for a land",
                      r"x is|costs? \{?\d*\}? less|for each land you control"),
}
_MAX_SYNERGY_LINES = 6


def synergy_lines(names, facts, tags, weights, commanders):
    """Two-card engines the deck is actually built around.

    Pairs the highest-weighted enabler with the highest-weighted payoff for
    the deck's dominant tags. Capped, because 800 enablers x 800 payoffs is a
    combinatorial explosion and the shim treats every line as something worth
    chasing. Commanders are allowed as a piece: they are always castable, which
    is exactly what makes a precon engine reliable.
    """
    out = []
    for tag in tags[:2]:
        pat = SYNERGY_LINES.get(tag)
        if not pat:
            continue
        en_re, pay_re = re.compile(pat[0], re.I), re.compile(pat[1], re.I)
        enablers, payoffs = [], []
        for n in names:
            f = facts.get(cards.key(n)) or facts.get(n) or {}
            text = f.get("oracle_text") or ""
            tline = f.get("type_line") or ""
            if "Land" in tline and "Creature" not in tline:
                continue
            w = weights.get(n, 1)
            if en_re.search(text):
                enablers.append((w, n))
            if pay_re.search(text):
                payoffs.append((w, n))
        enablers.sort(reverse=True)
        payoffs.sort(reverse=True)
        for _, e in enablers[:3]:
            for _, p in payoffs[:3]:
                if e == p:
                    continue
                pair = {e, p}
                if any(pair == set(l["cards"]) for l in out):
                    continue
                out.append({"cards": sorted(pair), "produces": [tag],
                            "source": "synergy"})
                if len(out) >= _MAX_SYNERGY_LINES:
                    return out
    return out


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
    # Lines cross the GPL boundary as data: the shim tracks their completion
    # and steers tutors/casting, but only when a line is nearly done (the
    # line-of-sight gate) — knowledge here, mechanism there.
    combo_pieces: set[str] = set()
    lines: list[dict] = []
    try:
        combo = combos.combos_for_dck(path, fetch=fetch)
        for v in (combo or {}).get("included", []):
            pieces = v.get("cards", [])
            combo_pieces.update(pieces)
            lines.append({"cards": pieces, "produces": v.get("produces", [])})
        # Fewest pieces first: shorter lines are the achievable ones, and the
        # shim prefers the most-complete line when steering a tutor.
        lines.sort(key=lambda ln: len(ln["cards"]))
    except Exception:
        pass  # no cache and no network — plans work without combos


    weights: dict[str, int] = {}
    roles: dict[str, str] = {}
    tutors: list[str] = []
    for n in names:
        f = facts.get(cards.key(n)) or facts.get(n) or {}
        text = f.get("oracle_text") or ""
        tline = f.get("type_line") or ""
        cmc = f.get("cmc") or 0
        if "Land" in tline and "Creature" not in tline:
            roles[n] = "land"
            continue
        tm = _TUTOR_CLAUSE.search(text)
        if tm and not _LAND_CLAUSE.search(tm.group(1)):
            tutors.append(n)
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

    # Every nonland tutor earns plan weight (task 20 Stage 1). It used to be
    # gated on known combo lines, which left tutor-dense decks with no reason
    # to keep or cast their tutors; a tutor is a path to whatever the search
    # ranking (below) values, lines or not.
    for n in tutors:
        if weights.get(n, 0) < 5:
            weights[n] = 5
            if roles.get(n, "filler") == "filler":
                roles[n] = "tutor"

    # Search-target values (task 20 Stage 1): what a resolved library search
    # should take, on its OWN scale. Keep weights above answer "is this card
    # a reason to keep a hand"; target values answer "is this card worth a
    # search right now". Stage 0 measured why they must not be the same
    # number: ranking fetch options by keep weights picks mana rocks over
    # Portal to Phyrexia in round 8 (studies/tutor_targeting).
    #
    # Scale: combo piece / finisher text 8, tagged payoff 7, expensive bomb
    # the tags missed (cmc >= 6) 6, cheap mana source 5 but only before round
    # `beforeRound`, protection 4, removal 3. Cards not listed are worth 1
    # implicitly. Context hints are data the shim checks against its own
    # battlefield at search time: `ramp` decays after beforeRound (table
    # rounds, not Forge player-turns); `finisher` needs minCreatures of your
    # own first (the Finale of Devastation case). Commanders live in the
    # command zone and are omitted.
    targets: dict[str, int] = {}
    context: dict[str, dict] = {}
    for n in names:
        if n in commanders:
            continue
        f = facts.get(cards.key(n)) or facts.get(n) or {}
        text = f.get("oracle_text") or ""
        tline = f.get("type_line") or ""
        cmc = f.get("cmc") or 0
        if "Land" in tline and "Creature" not in tline:
            continue
        if n in combo_pieces or _FINISHER.search(text):
            val = 8
        elif roles.get(n) == "payoff":
            val = 7
        elif cmc >= 6:
            val = 6
        elif _MANA_SOURCE.search(text) and cmc <= 3:
            val = 5
            context[n] = {"hint": "ramp", "beforeRound": 5}
        elif roles.get(n) == "protection":
            val = 4
        elif roles.get(n) == "removal":
            val = 3
        else:
            val = 1
        if val >= 6 and _BOARD_PAYOFF.search(text):
            context[n] = {"hint": "finisher", "minCreatures": 3}
        if val > 1:
            targets[n] = val

    # Spellbook knows nothing about precon-level engines: queried for all 66
    # Commander precons it returns ZERO variants. Fall back to the deck's own
    # archetype so "assemble your engine" means something on the decks most
    # players own. Only when Spellbook returned nothing -- a real catalogued
    # combo is always the better line.
    if not lines:
        lines = synergy_lines(names, facts, tags, weights, commanders)

    keep = sorted((n for n, w in weights.items() if w >= 5),
                  key=lambda n: -weights[n])[:16]
    threat = sorted((n for n, w in weights.items() if w >= 7), key=lambda n: -weights[n])
    personality = dict(TAG_PERSONALITY.get(tags[0] if tags else "_default",
                                           TAG_PERSONALITY["_default"]))

    # Provenance: how much of the deck the card-fact cache could actually
    # see. A cold cache silently degrades every heuristic above (no oracle
    # text, no cmc, no combo lines) — Stage 0 of task 20 ran that way and
    # nothing said so. The shim ignores this key; run_sim warns on it.
    known = sum(1 for n in names if (facts.get(cards.key(n)) or facts.get(n)))
    coverage = round(known / max(1, len(names)), 3)

    plan = {
        "factsCoverage": coverage,
        "tags": tags,
        "mulligan": {"minLands": 2, "maxLands": 5, "maxMulls": 2, "keepCards": keep},
        "weights": {n: w for n, w in weights.items() if w > 1},
        "threat": threat,
        "roles": roles,           # for the UI / coaching; the shim ignores it
        "personality": personality,
        "lines": lines,           # known combo piece-sets, fewest pieces first
        "tutors": tutors,         # nonland tutors — the line-of-sight gate's reach
        # Additive (task 20 Stage 1): shims before 0.4.2 ignore this key.
        "search": {"targets": targets, "context": context},
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
