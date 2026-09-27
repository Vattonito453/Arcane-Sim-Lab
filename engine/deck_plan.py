#!/usr/bin/env python3
"""Build a deck's play plan — the strategy data the sim agent runs on.

The plan is the bridge in task 07's architecture: all card knowledge stays
here (our side of the GPL boundary) and crosses to simlab-forge-shim as
JSON. Oracle text is used for *strategy hints only* — Forge remains the sole
adjudicator of what happens in a game (CLAUDE.md invariant).

Sources: win-condition tag heuristics over oracle text (user-editable at
import later — task 07), card roles, and combo lines from combos.py's disk
cache when available.

Plan versions (repair plan WS5 T1 item 6, the tutoring hotfix). Version 1 is
the default and is byte-identical to the plans built before versions existed.
Version 2 is built only when asked (plan_version=2, or MTG_PLAN_VERSION=2 for
run_sim and this CLI) and adds, per deck:
  planVersion   2
  lines         only the WIN-BAND Spellbook lines (combo_bands v0): these
                drive the pilot's pursuit and the value 8
  threatLines   every Spellbook line (what `lines` holds in version 1); the
                shim reads it for opponent-facing logic
  search.graveyardTargets   {card: 1-9} for searches that put a card in the
                graveyard: reanimation targets (when the deck reanimates),
                flashback/escape/unearth-style cards, and instants and
                sorceries the commander can cast from the graveyard
  fix           the shim 0.17.0 hotfix flags, all true
and changes: engine-only line pieces lose the blanket value 8 and fall back
to their role tier; self-loss text ("you lose the game": Pact of Negation,
Final Fortune) and saboteur text no longer read as a finisher; every card
name in the plan (lines, threatLines, the search maps, and the deck-keyed
fields) is the name Forge uses; the threat list keeps version 1's cards, so
what opponents fear does not change.

Usage:
  python3 deck_plan.py <deck.dck> [more.dck ...] [--out plans.json] [--fetch]
                       [--plan-version 1|2]

Zero dependencies (stdlib + sibling modules).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cards  # noqa: E402
import combo_bands  # noqa: E402
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
#   politics 0       do not hold interaction because someone else has mana
# splitAttacks was originally bundled here as an error dial. It is not one:
# spreading attacks across opponents is often correct multiplayer play, and
# stock Forge's 98% single-target habit is the deviation. Measured in
# isolation (512 mixed precon games, 2026-08-29): win effect -2.5 pp, not
# significant (the CI comfortably includes zero), while defenders per attack
# declaration moved 1.03 -> 1.28, the first config to break the single-target
# habit. Shipped at 0.7 as a style dial with a measured bound, not an error.
# The cEDH corpus is a picture of STRONG human play, so "human-like" means
# converting, not erring. Any future proposal to re-introduce error has to
# earn it with a measured gain, not an argument about realism.
TAG_PERSONALITY: dict[str, dict] = {
    "go-wide-tokens": {"aggression": 0.7, "splitAttacks": 0.7, "blockiness": 0.5,
                       "counterThreshold": 6, "dangerLife": 8,
                       "grudgeWeight": 0.25, "kingmakerRatio": 1.6,
                       "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "voltron-commander-damage": {"aggression": 0.8, "splitAttacks": 0.7, "blockiness": 0.4,
                                 "counterThreshold": 6, "dangerLife": 8,
                                 "grudgeWeight": 0.3, "kingmakerRatio": 1.4,
                                 "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "spellslinger-burn": {"aggression": 0.6, "splitAttacks": 0.7, "blockiness": 0.5,
                          "counterThreshold": 4, "dangerLife": 10,
                          "grudgeWeight": 0.2, "kingmakerRatio": 1.6,
                          "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "stax-control": {"aggression": 0.35, "splitAttacks": 0.7, "blockiness": 0.75,
                     "counterThreshold": 4, "dangerLife": 12,
                     "grudgeWeight": 0.15, "kingmakerRatio": 1.8,
                     "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "mill": {"aggression": 0.35, "splitAttacks": 0.7, "blockiness": 0.75,
             "counterThreshold": 4, "dangerLife": 12,
             "grudgeWeight": 0.15, "kingmakerRatio": 1.8,
             "politics": 0.0, "triggerMiss": 0.0, "greed": 1.0},
    "_default": {"aggression": 0.55, "splitAttacks": 0.7, "blockiness": 0.6,
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
# Plan version 2 (repair plan WS5 T1 item 6). Version 1 above scores two
# kinds of card as a finisher that are not: self-loss text ("If you don't,
# you lose the game": Pact of Negation, Summoner's Pact, Final Fortune, Last
# Chance, Warrior's Oath) and saboteur text ("Whenever this creature deals
# combat damage to a player, ...", 191 of the 4,347 cached cards, almost all
# of them card-advantage creatures). The plan says drop "loses? the game";
# this drops only its second-person form. "lose the game" is the pilot's own
# loss; the third-person "loses the game" is an opponent's (Vraska the
# Unseen's assassins, "Target player loses the game") or the poison reminder
# text on poison cards, which are this deck's finisher, and it stays.
# Measured on the card cache: the five self-loss cards above are the only
# cards the "lose"/"loses" split moves.
_FINISHER_V2 = re.compile(r"wins? the game|loses the game|infect|"
                          r"damage can't be prevented", re.I)
# Search-target heuristics (task 20 Stage 1). Same vocabulary style as the
# tag markers: cheap oracle-text tests, no new inference regime.
_MANA_SOURCE = re.compile(r"add \{|add one mana|add two mana", re.I)
_BOARD_PAYOFF = re.compile(r"creatures? you control get \+|creatures you control gain", re.I)
# Punisher engines: permanents that hurt the table on their own clock. They
# carry no power and rarely a keep weight, so the threat list never named
# them, and the shim's threat read scored a Nekusar board of Iron Maiden plus
# Spiteful Visions below a lone 4/4 (sim_20260902_145933 game 1 turn 17; the
# whole pod then fed the 4/4 instead of the open punisher). One sentence must
# carry BOTH a recurring trigger on the table's own actions (each player's
# upkeep, a player drawing, the owner drawing or casting) AND damage or life
# loss to that player or every opponent. A first cut matched either half
# alone and swept in 95 of 4,347 cached cards, including Consecrated Sphinx,
# Smothering Tithe and every aristocrat payoff; a threat name scores 8 in
# the shim's index and that index also gates its counterspells, so breadth
# here is not free. Permanents only: the same phrases on a sorcery are burn.
_PUNISHER = re.compile(
    r"(?:at the beginning of each (?:opponent's|player's)"
    r"|whenever (?:a|an) (?:player|opponent) (?:draws|casts|attacks)"
    r"|whenever you (?:draw|cast))"
    r"[^.]*?"
    r"(?:deals? (?:\d+|x) damage to (?:that player|each opponent|each player)"
    r"|(?:that player|each opponent|they) loses? (?:\d+|x) life)",
    re.I,
)

# ---------------------------------------------------------- plan versions --
# Version 1 is today's plan, byte for byte. Version 2 is the tutoring hotfix's
# data (module docstring). Anything else is refused: a typo in the flag must
# not silently run the wrong arm of an experiment.
PLAN_VERSIONS = (1, 2)
PLAN_VERSION_ENV = "MTG_PLAN_VERSION"
# The shim 0.17.0 mechanisms this plan asks for. The shim treats a missing
# flag as false, so a version-1 plan (no "fix" key) behaves as 0.16.0 did.
V2_FIX = {"tutorReach": True, "commanderTutorZone": True,
          "noForcedChoices": True, "graveyardDest": True}

# Graveyard targets (version 2, `search.graveyardTargets`). When a search puts
# the card into the graveyard (Entomb, Buried Alive, Unmarked Grave) the shim
# ranks the options by these values; a card that is absent scores 0, so
# stock Forge's own pick stands when nothing here is offered. Oracle text is
# a strategy hint only, like every heuristic in this file: Forge decides what
# a card can actually do.
#
# Reanimation: one paragraph that returns or puts a creature (or permanent)
# card from a graveyard onto the battlefield. Reanimate, Exhume, Necromancy,
# Unburial Rites, Persist, Dread Return; Animate Dead's "Return enchanted
# creature card to the battlefield"; Living Death's exile-then-return;
# Victimize and Stitch Together, whose return sits in a later sentence.
# Three things are read out first, because each made a card that reanimates
# nothing look like one (measured on the card cache, review of 2026-09-27):
# reminder text in parentheses (manifest dread: "...into your graveyard ...
# if it's a creature card"), a graveyard that is only a destination
# ("into your graveyard": Genesis Wave, Wakanda Forever!), and an activated
# ability's cost ("Discard a creature card: Return target land card from
# your graveyard", Floral Evoker). The graveyard must be a source.
_GY_SOURCE = re.compile(r"\b(?:from|in)\s+(?:[\w'’]+\s+){0,3}?graveyards?\b"
                        r"|\blibrary and/or graveyard\b"
                        r"|\bgraveyards? from (?:your|a|their) library\b", re.I)
_TO_BATTLEFIELD = re.compile(r"\b(?:to|onto) the battlefield\b", re.I)
_RETURN_VERB = re.compile(r"\b(?:return|put)s?\b", re.I)
_CREATURE_CARD = re.compile(r"\b(?:creature|permanent) cards?\b|\benchanted creature card\b",
                            re.I)
_REMINDER = re.compile(r"\([^()]*\)")
# "{2}{B}, Sacrifice a creature: <effect>" and "-3: <effect>": the cost ends
# at the first colon outside quotes.
_COST = re.compile(r'^[^:"]*:\s+(.*)$', re.S)
# A capped reanimation ("permanent card with mana value 3 or less": Sevinne's
# Reclamation, Sun Titan, Angel of Indemnity) cannot return a bigger card.
_MV_CAP = re.compile(r"\bmana value (\d+) or less\b", re.I)
_NO_CAP = 99
# Keywords that let a card be cast, or put onto the battlefield, or used,
# from its owner's graveyard. Anchored to the start of a paragraph: that is
# where the card's OWN keyword sits, so "target instant card in your
# graveyard gains flashback" (Snapcaster Mage) is not read as Snapcaster
# having flashback. Harmonize, aftermath, encore, scavenge and dredge were
# added after review (Nature's Rhythm has harmonize). Mayhem is left out on
# purpose: it works only when the card was DISCARDED this turn, and a search
# that puts a card into the graveyard is not a discard.
_GY_KEYWORD = re.compile(r"(?:^|\n)(?:flashback|escape|unearth|retrace|jump-start|embalm|"
                         r"eternalize|disturb|harmonize|aftermath|encore|scavenge|dredge)\b",
                         re.I)
# A commander that casts instants or sorceries from the graveyard: Kess,
# Dissident Mage ("you may cast an instant or sorcery spell from your
# graveyard"), or one that grants them a graveyard keyword (Lier, Disciple of
# the Drowned: "Instant and sorcery cards in your graveyard have flashback").
_CMDR_GY_SPELLS = re.compile(
    r"\bcast (?:an? )?(?:instant|sorcery)(?: (?:or|and) sorcery)?(?: spells?| cards?)? "
    r"from your graveyard"
    r"|\b(?:instant|sorcery)(?: (?:or|and) sorcery)? cards? in your graveyard "
    r"ha(?:s|ve) (?:flashback|jump-start|retrace|escape)", re.I)


def _reanimation_reach(text: str) -> int | None:
    """The highest mana value this card can put onto the battlefield from a
    graveyard (_NO_CAP when uncapped), or None when it reanimates nothing."""
    reach = None
    for para in _REMINDER.sub("", text or "").split("\n"):
        cost = _COST.match(para)
        if cost:
            para = cost.group(1)
        if (_GY_SOURCE.search(para) and _TO_BATTLEFIELD.search(para)
                and _RETURN_VERB.search(para) and _CREATURE_CARD.search(para)):
            caps = [int(x) for x in _MV_CAP.findall(para)]
            here = max(caps) if caps else _NO_CAP
            reach = here if reach is None else max(reach, here)
    return reach


def _reanimates(text: str) -> bool:
    """Does this card put creature cards from a graveyard onto the battlefield?"""
    return _reanimation_reach(text) is not None


def env_plan_version() -> int:
    """MTG_PLAN_VERSION as an int: unset or empty means 1. Raises ValueError
    on anything but 1 or 2, so a mistyped flag fails the run loudly instead
    of running version 1 while the experiment log says version 2."""
    raw = (os.environ.get(PLAN_VERSION_ENV) or "").strip()
    if not raw:
        return 1
    if raw not in {str(v) for v in PLAN_VERSIONS}:
        raise ValueError(f"{PLAN_VERSION_ENV}={raw!r}: expected one of "
                         f"{', '.join(str(v) for v in PLAN_VERSIONS)}")
    return int(raw)


def _check_version(plan_version) -> int:
    if plan_version not in PLAN_VERSIONS:
        raise ValueError(f"plan_version={plan_version!r}: expected one of {PLAN_VERSIONS}")
    return plan_version


def forge_namer(deck_names: list[str]):
    """name -> the name Forge gives the card (Card.getName()), for version 2.

    Spellbook names a transform, modal, adventure or flip card "Front // Back"
    ("Birgi, God of Storytelling // Harnfel, Horn of Bounty"); Forge names it
    by its front face and a split card "A // B". A line whose piece is spelled
    the Spellbook way never matches the card Forge put on the battlefield, so
    the line can never complete. In order:
      1. Forge's own index (forge_index.resolve), when it is built;
      2. convert_decklist's normalisation: the Scryfall layout in the card
         cache (cache only, never the network);
      3. still "A // B" and its front face is a card in this deck while the
         joined name is not: the front face. The deck is exactly what Forge
         was given, so that is the card Forge loaded.
    A name none of these can place is returned unchanged."""
    deck = set(deck_names)
    try:
        import forge_index
        idx = forge_index.load_index()
    except Exception:  # noqa: BLE001 — no index: the fallbacks still run
        idx = None
    try:
        import convert_decklist
        fallback = convert_decklist._Names(None, convert_decklist._cached_facts)
    except Exception:  # noqa: BLE001
        fallback = None
    memo: dict[str, str] = {}

    def name_of(n: str) -> str:
        if n in memo:
            return memo[n]
        out = None
        if idx is not None:
            out = idx.resolve(n)
        if out is None and fallback is not None:
            fallback.prime([n])
            out = fallback(n)
        out = out or n
        if " // " in out and out not in deck:
            front = out.split(" // ", 1)[0].strip()
            if front in deck:
                out = front
        memo[n] = out
        return out

    return name_of


def _graveyard_targets(names: list[str], commanders: list[str], facts: dict,
                       targets: dict[str, int]) -> dict[str, int]:
    """search.graveyardTargets for version 2: {card: value 1-9}.

    (a) Reanimation targets, only when the deck reanimates (a reanimation
        spell or effect in the 99, or a commander that does it): creature
        cards, valued by what they are worth on the battlefield: by mana
        value (8+ -> 8, 6-7 -> 7, 4-5 -> 5), or the library-search value
        when that is 6 or more (a win piece such as Thassa's Oracle, a
        finisher, a payoff). A cheap creature below both has no graveyard
        value; neither does a mana dork on its early-ramp value of 5.
    (b) Cards with flashback, escape, unearth, retrace, jump-start, embalm,
        eternalize or disturb: castable (or returnable) from the graveyard.
    (c) Instants and sorceries, when the commander lets the deck cast them
        from its graveyard (Kess, Dissident Mage).
    (b) and (c) are valued at their library-search value with a floor of 3,
    so a cheap cantrip still outranks a card with no graveyard use. Anything
    else is absent (score 0: stock's pick stands), which is the whole point
    for Sol Ring. Commanders and lands are never listed.

    A card in a graveyard has only its front face's characteristics, so the
    land and creature tests read the front face: a modal spell whose back is
    a land ("Sink into Stupor // Soporific Springs") is an instant there,
    which Kess can cast. When every reanimation effect in the deck is capped
    ("mana value 3 or less": Sevinne's Reclamation) a creature above the cap
    is not a reanimation target."""
    def text_of(n: str) -> str:
        return _fact(facts, n).get("oracle_text") or ""

    def type_of(n: str) -> str:
        return _fact(facts, n).get("type_line") or ""

    reaches = [r for r in (_reanimation_reach(text_of(n)) for n in names) if r is not None]
    reach = max(reaches) if reaches else None
    cmdr_spells = any(_CMDR_GY_SPELLS.search(text_of(c)) for c in commanders)
    out: dict[str, int] = {}
    for n in names:
        if n in commanders or n in out:
            continue
        tline = type_of(n)
        front = tline.split(" // ", 1)[0]
        if not tline or ("Land" in front and "Creature" not in front):
            continue
        base = targets.get(n, 1)
        vals: list[int] = []
        cmc = _fact(facts, n).get("cmc") or 0
        if reach is not None and "Creature" in front and cmc <= reach:
            tier = 8 if cmc >= 8 else 7 if cmc >= 6 else 5 if cmc >= 4 else 0
            # A search value of 6+ (win piece, finisher, payoff, bomb) carries
            # over; 5 is the early-ramp value, and a mana dork is not what a
            # reanimation spell is for.
            val = max(tier, base if base >= 6 else 0)
            if val:
                vals.append(val)
        if _GY_KEYWORD.search(text_of(n)):
            vals.append(max(base, 3))
        if cmdr_spells and ("Instant" in tline or "Sorcery" in tline):
            vals.append(max(base, 3))
        if vals:
            out[n] = max(1, min(9, max(vals)))
    return out


def _fact(facts: dict, n: str) -> dict:
    """One card's facts under either key style callers use."""
    return facts.get(cards.key(n)) or facts.get(n) or {}


# Synergy lines: a deck's win condition when Commander Spellbook has nothing.
#
# Spellbook catalogues competitive and infinite combos. This comment used to
# say Spellbook returns no variants for any of the 66 Commander precons.
# Corrected 2026-09-26: false. combos.parse_dck sent Forge's "|SET|art" suffix
# with each name; with clean names 14 of 66 precons have 26 included variants
# (and 65 of 66 have almost-included ones). The suffix exists only in Forge's
# bundled precon files, not in engine/decks or convert_decklist output, so
# user-imported decks were never affected. Even with clean names 52 of 66
# precons have no included variants, so `lines` stays empty on most of
# Forge's bundled precons and the shim's combo pursuit is inert there. But a
# precon absolutely has a win
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
            f = _fact(facts, n)
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


def build_plan(path: str | Path, fetch: bool = False,
               synergy: bool = False, plan_version: int = 1) -> tuple[str, dict]:
    """(deck name, plan). plan_version 1 (the default) is byte-identical to
    the plans built before versions existed; 2 is the tutoring hotfix's data
    (module docstring). Callers that should honour MTG_PLAN_VERSION pass
    env_plan_version(); build_plans does that by default."""
    v2 = _check_version(plan_version) == 2
    finisher_re = _FINISHER_V2 if v2 else _FINISHER
    deck_name, commanders, main = read_dck(path)
    names = commanders + main
    facts = cards.get_many(names, fetch=fetch)

    # Tag scoring: how many cards support each tag.
    tag_hits: dict[str, list[str]] = {t: [] for t in TAG_MARKERS}
    for n in names:
        f = _fact(facts, n)
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
    #
    # Version 1: every Spellbook variant is a pilot line and every piece of
    # one is a combo piece (value 8). Version 2: only win-band lines
    # (combo_bands.is_win_band) are pilot lines and give their pieces the 8;
    # every line still goes to threatLines, which the shim reads for what
    # OPPONENTS fear, so narrowing the pilot's list does not blind the table.
    combo_pieces: set[str] = set()   # v1: every line piece; v2: win-band pieces
    lines: list[dict] = []           # v1: every line; v2: win-band lines only
    threat_lines: list[dict] = []    # v2 only: every line
    threat_pieces: set[str] = set()  # v2 only: every line piece
    # Version 2 only: Spellbook's spelling becomes Forge's (forge_namer).
    # Version 1 keeps Spellbook's spelling, because version 1 must stay
    # byte-identical to the plans built before versions existed.
    name_of = forge_namer(names) if v2 else None

    # A deck card as the line pieces spell it. Version 2's pieces are in
    # Forge's spelling, so a deck that still spells a card the Spellbook way
    # ("Birgi, God of Storytelling // Harnfel, Horn of Bounty") is mapped
    # before the membership test, or its own line piece would not count.
    def as_piece(n: str) -> str:
        return name_of(n) if name_of else n

    try:
        combo = combos.combos_for_dck(path, fetch=fetch)
        for v in (combo or {}).get("included", []):
            pieces = v.get("cards", [])
            if not v2:
                combo_pieces.update(pieces)
                lines.append({"cards": pieces, "produces": v.get("produces", [])})
                continue
            mapped = list(dict.fromkeys(name_of(c) for c in pieces))
            produces = list(v.get("produces", []))
            threat_lines.append({"cards": mapped, "produces": produces})
            threat_pieces.update(mapped)
            if combo_bands.is_win_band(v):
                lines.append({"cards": list(mapped), "produces": list(produces)})
                combo_pieces.update(mapped)
        # Fewest pieces first: shorter lines are the achievable ones, and the
        # shim prefers the most-complete line when steering a tutor.
        lines.sort(key=lambda ln: len(ln["cards"]))
        threat_lines.sort(key=lambda ln: len(ln["cards"]))
    except Exception:
        pass  # no cache and no network — plans work without combos


    weights: dict[str, int] = {}
    roles: dict[str, str] = {}
    tutors: list[str] = []
    mana_creatures: list[str] = []
    # Version 2 only: the cards version 1 weighted 8 that version 2 does not
    # (engine pieces, and payoffs whose only finisher text was self-loss or
    # saboteur text). They stay in the threat list below (see there).
    v1_threats: set[str] = set()
    for n in names:
        f = _fact(facts, n)
        text = f.get("oracle_text") or ""
        tline = f.get("type_line") or ""
        cmc = f.get("cmc") or 0
        if "Land" in tline and "Creature" not in tline:
            roles[n] = "land"
            continue
        if "Creature" in tline and _MANA_SOURCE.search(text):
            mana_creatures.append(n)
        tm = _TUTOR_CLAUSE.search(text)
        if tm and not _LAND_CLAUSE.search(tm.group(1)):
            tutors.append(n)
        if v2 and (as_piece(n) in threat_pieces
                   or (n in tag_cards and _FINISHER.search(text))):
            v1_threats.add(n)
        # Version 2: an engine-only line piece is not in combo_pieces, so it
        # falls through to its role tier below instead of the blanket 8.
        if as_piece(n) in combo_pieces:
            roles[n], weights[n] = "combo-piece", 8
        elif n in tag_cards and (finisher_re.search(text) or cmc >= 4):
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
        f = _fact(facts, n)
        text = f.get("oracle_text") or ""
        tline = f.get("type_line") or ""
        cmc = f.get("cmc") or 0
        if "Land" in tline and "Creature" not in tline:
            continue
        if as_piece(n) in combo_pieces or finisher_re.search(text):
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

    # Fallback when Spellbook returns no lines for a deck. The premise was that
    # Spellbook returns nothing for any precon; corrected 2026-09-26: false,
    # that was combos.parse_dck's "|SET|art" suffix bug (clean names: 14 of 66
    # precons have 26 included variants). Falls back to the deck's own
    # archetype so "assemble your engine" means something when there is no
    # catalogued line. Only when Spellbook returned nothing -- a real catalogued
    # combo is always the better line. The repair plan (section 8) does not
    # revive this fallback.
    # OPT-IN until validated. The one arm that ran with synergy lines on
    # predicted WORSE than stock (rank corr 0.255 -> 0.142), though it was
    # undersampled and censored so that is not a clean refutation. Either way
    # it has not earned being on by default.
    if not v2:
        if synergy and not lines:
            lines = synergy_lines(names, facts, tags, weights, commanders)
    elif synergy and not threat_lines:
        # Version 2: a synergy line is an archetype engine ("tokens, then
        # anthem"), which combo_bands does not read as a win, so it is a
        # threat line and never a pilot line. Its pieces are deck cards,
        # mapped to Forge's spelling like every other name in version 2.
        threat_lines = [dict(ln, cards=list(dict.fromkeys(name_of(c) for c in ln["cards"])))
                        for ln in synergy_lines(names, facts, tags, weights, commanders)]
        lines = [ln for ln in threat_lines if combo_bands.is_win_band(ln)]

    graveyard_targets: dict[str, int] = {}
    if v2:
        graveyard_targets = _graveyard_targets(names, commanders, facts, targets)

    keep = sorted((n for n, w in weights.items() if w >= 5),
                  key=lambda n: -weights[n])[:16]
    # Threat signature v2. Weight >= 7 alone starved board-centric decks:
    # measured on Vincent's pod, the dragon deck carried 9 threat cards to the
    # artifact decks' 19-27, because generic big bodies score 6 (the cmc-bomb
    # tier) or less. The table's threat index is built FROM these lists, so a
    # board of huge dragons read as low-threat while a token swarm lit the
    # index up -- and the deck that actually won the pod (4 of 8, then 10 of
    # 16) was attacked LEAST. A big body is a threat whatever its keep-weight
    # says, and the commander always is.
    def _pow(n: str) -> int:
        f = _fact(facts, n)
        if "creature" not in (f.get("type_line") or "").lower():
            return 0
        try:
            return int(f.get("power") or 0)
        except (TypeError, ValueError):
            return 0  # '*' powers stay out; the shim reads live P/T anyway
    def _punisher(n: str) -> bool:
        f = _fact(facts, n)
        if not any(t in (f.get("type_line") or "") for t in cards.PERMANENT_TYPES):
            return False
        return bool(_PUNISHER.search(f.get("oracle_text") or ""))
    threat_set = {n for n, w in weights.items() if w >= 7}
    threat_set |= {n for n in set(names) if _pow(n) >= 5}
    threat_set |= {n for n in set(names) if _punisher(n)}
    threat_set |= set(commanders)
    if v2:
        # The threat list is what OPPONENTS fear: the shim builds the table's
        # threat index from it (at 8) and that index gates their counterspells.
        # Version 1 put every nonland line piece and every tagged card with
        # finisher text here through a weight of 8. Version 2 lowers those
        # weights for the PILOT (it stops chasing Sol Ring, and Pact of
        # Negation is no longer a finisher it keeps or fetches), but keeps
        # them here, so the table's threat read is version 1's and the hotfix
        # changes only the pilot's own data. Measured on 126 decks: without
        # this, 101 cards (saboteur creatures such as Ragavan, and Pact of
        # Negation) left the threat lists and the counterspell guard at G0a
        # would have measured that too.
        threat_set |= v1_threats
        # Ties broken by name. Version 1 leaves them in set order, which
        # follows the per-process string hash seed, so two builds of the same
        # deck can list its threats in different orders. Version 2 is new, so
        # it can be reproducible byte for byte without moving version 1.
        threat = sorted(threat_set, key=lambda n: (-weights.get(n, 0), -_pow(n), n))
    else:
        threat = sorted(threat_set, key=lambda n: (-weights.get(n, 0), -_pow(n)))
    personality = dict(TAG_PERSONALITY.get(tags[0] if tags else "_default",
                                           TAG_PERSONALITY["_default"]))
    # Threat model v2: how loudly an opponent's nearly-complete combo line
    # (all but one piece visible on their board) rings the table alarm.
    # Shipped explicitly rather than relying on the shim default, so the
    # value is on the record in every plans file.
    personality.setdefault("lineProximity", 6)
    # openThreatShare (shim 0.14.0): an attacker aimed at a player who has an
    # untapped creature that can block it is re-aimed at the highest-threat
    # OTHER opponent with no such blocker, if that opponent's threat is at
    # least this share of the current target's. Measured need:
    # sim_20260902_145933 game 1 turn 17, a 2/2 and a 1/1 sent into an
    # untapped 4/4 while the punisher deck sat open two threat points back.
    # One value for every archetype, so shipped here rather than per profile.
    # 0 disables.
    personality.setdefault("openThreatShare", 0.6)
    # holdInstants / holdInstantUntilRound (shim 0.15.0, task 21 Half 1): on
    # its own turn with an empty stack, the agent keeps an instant-speed
    # answer aimed at an opponent's permanent and casts its best other spell
    # instead, so the answer is still in hand when an opponent's turn gives
    # it a reason. Measured need (studies/precon_predict, 256 stock + 332
    # agent games): 78% of instants were cast on the caster's own turn and
    # only 2.7% of all spells off-turn. P(hold) per card per turn; the hold
    # stops applying after the cutoff round. 0 disables either.
    personality.setdefault("holdInstants", 1.0)
    personality.setdefault("holdInstantUntilRound", 10)
    # combatSolver / priorityGates (shim 0.16.0): the branch-and-bound combat
    # solver and the stack/priority gates from the engine A/B
    # (studies/engine_ab). OFF until that A/B says otherwise; shipped
    # explicitly so the plans file records the decision.
    personality.setdefault("combatSolver", 0.0)
    personality.setdefault("priorityGates", 0.0)

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
        # Creatures that tap for mana. They belong at home making mana, not
        # attacking, and they are the first body the agent keeps back when it
        # holds blockers. (Stock Forge already gets this right 98.3% of the
        # time -- measured -- so this protects a good behaviour rather than
        # fixing a bad one.)
        "manaCreatures": mana_creatures,
        # Additive (task 20 Stage 1): shims before 0.4.2 ignore this key.
        "search": {"targets": targets, "context": context},
    }
    if v2:
        plan = _as_v2(plan, threat_lines, graveyard_targets, name_of)
    # Outcome feedback: let observed win methods NUDGE the plan (bounded,
    # search targets only). The cold-start invariant lives in plan_feedback:
    # a deck with no history gets exactly the plan built above, and a broken
    # store must never block a plan from building at all.
    # OFF unless MTG_PLAN_FEEDBACK_APPLY=1 (repair plan WS0 task 5, RC4): the
    # nudge was never validated, and with it on a plan depends on whatever
    # the store happened to hold. note_tags still runs; it records the
    # archetype and never changes the plan. Plans are built in run_sim, so
    # the flag that matters is the WORKER's; deploy/preflight.py asserts it.
    try:
        import plan_feedback
        plan_feedback.note_tags(deck_name, tags)
        if os.environ.get("MTG_PLAN_FEEDBACK_APPLY", "0") == "1":
            plan = plan_feedback.apply_to_plan(plan, deck_name, tags)
    except Exception:
        pass
    return deck_name, plan


def _as_v2(plan: dict, threat_lines: list[dict], graveyard_targets: dict[str, int],
           name_of) -> dict:
    """The version-2 layout: planVersion first, threatLines beside lines,
    search.graveyardTargets, the fix flags, and every card name in Forge's
    spelling. Line cards were mapped when the lines were read.

    The contract names lines, threatLines and the search maps; the deck-keyed
    fields (weights, threat, keepCards, tutors, manaCreatures, roles) are
    mapped too, because the shim matches every one of them against
    Card.getName(). For a deck that came through the import (which already
    writes Forge's names) this is the identity; it matters for a precon whose
    file spells a name in another case than Forge ("They Came From the
    Pipes") and for a study deck pasted as "Front // Back"."""
    def remap(d: dict) -> dict:
        out: dict = {}
        for k, v in d.items():
            fk = name_of(k)
            if fk in out and isinstance(v, int):
                out[fk] = max(out[fk], v)   # two spellings of one card: keep the higher
            else:
                out.setdefault(fk, v)
        return out

    def relist(xs: list[str]) -> list[str]:
        return list(dict.fromkeys(name_of(x) for x in xs))

    search = plan["search"]
    out: dict = {"planVersion": 2}
    for k, v in plan.items():
        if k == "search":
            out[k] = {"targets": remap(search["targets"]),
                      "context": remap(search["context"]),
                      "graveyardTargets": remap(graveyard_targets)}
            continue
        if k in ("weights", "roles"):
            v = remap(v)
        elif k in ("threat", "tutors", "manaCreatures"):
            v = relist(v)
        elif k == "mulligan":
            v = dict(v, keepCards=relist(v.get("keepCards") or []))
        out[k] = v
        if k == "lines":
            out["threatLines"] = threat_lines   # every line; the shim's opponent logic
    out["fix"] = dict(V2_FIX)
    return out


def build_plans(paths: list[str | Path], fetch: bool = False,
                synergy: bool = False, plan_version: int | None = None) -> dict:
    """{"decks": {name: plan}}. plan_version None reads MTG_PLAN_VERSION
    (unset: 1), which is how run_sim and the CLI honour the flag."""
    version = env_plan_version() if plan_version is None else _check_version(plan_version)
    decks = {}
    for p in paths:
        name, plan = build_plan(p, fetch=fetch, synergy=synergy, plan_version=version)
        decks[name] = plan
    return {"decks": decks}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("decks", nargs="+", help=".dck files")
    ap.add_argument("--out", default=None, help="write plans JSON here (default stdout)")
    ap.add_argument("--synergy", action="store_true",
                    help="derive combo lines from the deck's archetype when "
                         "Spellbook has none (UNVALIDATED: see "
                         "studies/precon_predict/README.md)")
    ap.add_argument("--fetch", action="store_true",
                    help="allow Scryfall/Spellbook network fetches (cache-only otherwise)")
    ap.add_argument("--plan-version", type=int, choices=PLAN_VERSIONS, default=None,
                    help=f"plan version to build (default: ${PLAN_VERSION_ENV}, else 1)")
    args = ap.parse_args()
    plans = build_plans(args.decks, fetch=args.fetch, synergy=args.synergy,
                        plan_version=args.plan_version)
    payload = json.dumps(plans, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        for name, plan in plans["decks"].items():
            extra = ""
            if plan.get("planVersion", 1) >= 2:
                extra = (f" v{plan['planVersion']} lines={len(plan['lines'])}"
                         f"/{len(plan['threatLines'])} "
                         f"graveyardTargets={len(plan['search']['graveyardTargets'])}")
            print(f"{name}: tags={plan['tags']} keeps={len(plan['mulligan']['keepCards'])} "
                  f"threat={len(plan['threat'])}{extra}")
        print(f"wrote {args.out}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
