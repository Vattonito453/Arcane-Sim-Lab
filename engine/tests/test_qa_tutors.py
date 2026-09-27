#!/usr/bin/env python3
"""qa/tutors: tutor reach, fates, graveyard steers, timing and the guard.

Offline and synthetic by construction: every card here is invented, the
search facts are hand-written in tutors.json's shape (never read from Forge's
card scripts, which are GPL and never committed), and the card facts are a
small in-memory cache. Nothing touches engine/card_cache.json or a real run.

Run: py engine/tests/test_qa_tutors.py -> ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from qa import context as qctx  # noqa: E402
from qa import tutors  # noqa: E402
from qa.tutors import COND, SKIP, Reach, clause_verdict, combine_verdicts  # noqa: E402

A, B = "Ai(1)-Alpha", "Ai(2)-Beta"

SEARCHES = {
    "Scholar's Query": [{"via": "SP", "destination": "Hand", "change_type": "Instant,Sorcery"}],
    "Verdant Call": [{"via": "SP", "destination": "Battlefield", "change_type": "Creature.cmcLEX"}],
    "Grave Whisper": [{"via": "SP", "destination": "Graveyard", "change_type": "Card.!Legendary"}],
    "Mind Shuffle": [{"via": "K", "keyword": "Transmute", "destination": "Hand",
                      "change_type": "Card.sameCMC"}],
    "Deep Search": [{"via": "SP", "destination": "Hand", "change_type": "Card"}],
    "Top Seer": [{"via": "SP", "destination": "Library", "library_position": "0",
                  "change_type": "Card"}],
    "Pod Engine": [{"via": "AB", "destination": "Battlefield", "change_type": "Creature.cmcEQX"}],
    "Twin Omens": [{"via": "SP", "destination": "Library", "change_type": "Card"},
                   {"via": "DB", "svar": "Pick", "destination": "Hand",
                    "change_type": "Card.IsRemembered"}],
}
TYPES = {
    "Scholar's Query": "Sorcery", "Verdant Call": "Sorcery", "Grave Whisper": "Sorcery",
    "Mind Shuffle": "Instant", "Deep Search": "Sorcery", "Top Seer": "Instant",
    "Pod Engine": "Artifact", "Twin Omens": "Instant", "Iron Idol": "Artifact",
    "Tide Oracle": "Creature Merfolk Wizard", "Big Finish": "Instant", "Rust Ring": "Artifact",
    "Rot Titan": "Creature Zombie Giant", "Final Portal": "Artifact",
    "Kessa, Grave Scholar": "Legendary Creature Human Wizard", "Rise Again": "Sorcery",
    "Gear Golem": "Artifact Creature Golem", "Moss Hound": "Creature Elemental Hound",
}


def fact(type_line, cmc, colors=(), power=None, oracle=""):
    return {"type_line": type_line, "cmc": cmc, "colors": list(colors), "power": power,
            "oracle_text": oracle}


CACHE = {
    "mind shuffle": fact("Instant", 1, ["U"], oracle="Counter target spell. Transmute {1}{U}{U}"),
    "iron idol": fact("Artifact", 1),
    "tide oracle": fact("Creature \u2014 Merfolk Wizard", 2, ["U"], "1"),
    "big finish": fact("Instant", 3, ["R"], oracle="Big Finish deals 3 damage to any target."),
    "rust ring": fact("Artifact", 1, oracle="{T}: Add {C}{C}."),
    "rot titan": fact("Creature \u2014 Zombie Giant", 6, ["B"], "6", "Deathtouch"),
    "kessa, grave scholar": fact(
        "Legendary Creature \u2014 Human Wizard", 3, ["U", "B", "R"], "2",
        "During each of your turns, you may cast an instant or sorcery card from your graveyard."),
    "rise again": fact("Sorcery", 5, ["B"],
                       oracle="Return target creature card from your graveyard to the battlefield."),
    "final portal": fact("Artifact", 9),
    "gear golem": fact("Artifact Creature \u2014 Golem", 3, (), "3"),
    "moss hound": fact("Creature \u2014 Elemental Hound", 2, ["G"], "2"),
}

PLANS = {"decks": {
    "Alpha": {
        "tutors": ["Scholar's Query", "Verdant Call", "Grave Whisper", "Mind Shuffle",
                   "Deep Search", "Kessa, Grave Scholar"],
        "roles": {"Kessa, Grave Scholar": "commander", "Rise Again": "filler",
                  "Rot Titan": "filler", "Big Finish": "filler", "Rust Ring": "filler",
                  "Tide Oracle": "combo-piece", "Iron Idol": "combo-piece"},
        "closers": ["Final Portal"],
        "search": {"targets": {"Rust Ring": 8}},
    },
    "Beta": {"tutors": ["Top Seer", "Deep Search"], "roles": {"Gear Golem": "filler"}},
}}


def Z(turn, phase, card, cid, frm, to, fp, tp, types=""):
    return {"turn": turn, "phase": phase, "card": card, "cardId": cid, "from": frm, "to": to,
            "fromPlayer": fp, "toPlayer": tp, "types": types, "pt": "", "token": False}


def AG(turn, player, event, detail):
    return {"turn": turn, "player": player, "event": event, "detail": detail}


def cast(player, card):
    return {"action": "stack_add", "raw": f"{player} cast {card}", "object": card}


def res(text):
    return {"action": "stack_resolve", "raw": text}


def SS(sid, dest, missing, picked, src, combo="-"):
    return (f"sid={sid} options=20 sighted=true mode=targets ranked=3 agree=false pickedW=6 "
            f"planW=8 dest={dest} comboPick={combo} missing={missing} picked={picked} "
            f"planPick=- src={src}")


def game0():
    zones = [
        Z(0, "", "Scholar's Query", 11, "Library", "Hand", A, A, "Sorcery"),
        Z(0, "", "Verdant Call", 12, "Library", "Hand", A, A, "Sorcery"),
        Z(0, "", "Grave Whisper", 13, "Library", "Hand", A, A, "Sorcery"),
        Z(0, "", "Mind Shuffle", 14, "Library", "Hand", A, A, "Instant"),
        Z(0, "", "Top Seer", 21, "Library", "Hand", B, B, "Instant"),
        Z(0, "", "Deep Search", 22, "Library", "Hand", B, B, "Sorcery"),
        Z(3, "MAIN1", "Scholar's Query", 11, "Hand", "Stack", A, ""),
        Z(3, "MAIN1", "Big Finish", 31, "Library", "Hand", A, A, "Instant"),
        Z(3, "MAIN1", "Scholar's Query", 11, "Stack", "Graveyard", "", A),
        Z(3, "MAIN1", "Big Finish", 31, "Hand", "Stack", A, ""),
        Z(3, "MAIN1", "Big Finish", 31, "Stack", "Graveyard", "", A),
        Z(3, "END_OF_TURN", "Top Seer", 21, "Hand", "Stack", B, ""),
        Z(3, "END_OF_TURN", "Gear Golem", 41, "Library", "Library", B, B, "Creature,Artifact"),
        Z(3, "END_OF_TURN", "Top Seer", 21, "Stack", "Graveyard", "", B),
        Z(4, "DRAW", "Gear Golem", 41, "Library", "Hand", B, B, "Creature,Artifact"),
        Z(4, "MAIN2", "Deep Search", 22, "Hand", "Stack", B, ""),
        Z(4, "MAIN2", "Moss Hound", 42, "Library", "Hand", B, B, "Creature"),
        Z(4, "MAIN2", "Deep Search", 22, "Stack", "Graveyard", "", B),
        Z(5, "MAIN2", "Verdant Call", 12, "Hand", "Stack", A, ""),
        Z(5, "MAIN2", "Verdant Call", 12, "Stack", "Graveyard", "", A),
        Z(6, "MAIN1", "Tide Oracle", 32, "Library", "Graveyard", A, A, "Creature"),
        Z(7, "MAIN1", "Grave Whisper", 13, "Hand", "Stack", A, ""),
        Z(7, "MAIN1", "Rust Ring", 33, "Library", "Graveyard", A, A, "Artifact"),
        Z(7, "MAIN1", "Grave Whisper", 13, "Stack", "Graveyard", "", A),
        Z(9, "MAIN1", "Mind Shuffle", 14, "Hand", "Stack", A, ""),
        Z(9, "MAIN1", "Mind Shuffle", 14, "Stack", "Hand", "", A),
    ]
    turns = [
        {"turn": 3, "active_player": A, "events": [
            cast(A, "Scholar's Query"), res("Scholar's Query (11) - Search your library."),
            cast(A, "Big Finish"), res("Big Finish (31) - Big Finish deals 3 damage to Ai(2)-Beta."),
            cast(B, "Top Seer"), res("Top Seer (21) - Search your library.")]},
        {"turn": 4, "active_player": B, "events": [
            cast(B, "Deep Search"), res("Deep Search (22) - Search your library.")]},
        {"turn": 5, "active_player": A, "events": [
            cast(A, "Verdant Call"),
            res("Verdant Call (12) - Search your library for a creature card. (X=0)")]},
        {"turn": 6, "active_player": B, "events": []},
        {"turn": 7, "active_player": A, "events": [
            cast(A, "Grave Whisper"), res("Grave Whisper (13) - Search your library.")]},
        {"turn": 8, "active_player": B, "events": []},
        {"turn": 9, "active_player": A, "events": [
            {"action": "stack_add",
             "raw": "Mind Shuffle (14) - [Couldn't add to stack, failed to target] - Counter "
                    "target spell."}]},
    ]
    agents = [
        AG(0, A, "mull_keep", "lands=3 planCard=true size=7"),
        AG(3, A, "tutor_cast", "Scholar's Query seeking Tide Oracle"),
        AG(3, A, "search_seen", SS(1, "Hand", "Tide Oracle", "Big Finish", "Scholar's Query")),
        AG(5, A, "tutor_cast", "Verdant Call seeking Tide Oracle"),
        AG(7, A, "tutor_cast", "Grave Whisper seeking Tide Oracle"),
        AG(7, A, "search_seen", SS(2, "Graveyard", "Tide Oracle", "Rot Titan", "Grave Whisper")),
        AG(7, A, "tutor_steer", "sid=2 mode=plan value=8 stockValue=6 steer=Rust Ring over=Rot Titan"),
        AG(9, A, "tutor_cast", "Mind Shuffle seeking Iron Idol"),
    ]
    return {"players": [A, B], "turns": turns, "zones": zones, "agent_events": agents,
            "result": {"winner": B, "draw": False}}


def game1():
    zones = [
        Z(0, "", "Deep Search", 51, "Library", "Hand", A, A, "Sorcery"),
        Z(0, "", "Grave Whisper", 52, "Library", "Hand", A, A, "Sorcery"),
        Z(2, "MAIN1", "Grave Whisper", 52, "Hand", "Stack", A, ""),
        Z(2, "MAIN1", "Big Finish", 61, "Library", "Graveyard", A, A, "Instant"),
        Z(2, "MAIN1", "Grave Whisper", 52, "Stack", "Graveyard", "", A),
        Z(2, "MAIN2", "Deep Search", 51, "Hand", "Stack", A, ""),
        Z(2, "MAIN2", "Rust Ring", 62, "Library", "Hand", A, A, "Artifact"),
        Z(2, "MAIN2", "Deep Search", 51, "Stack", "Graveyard", "", A),
    ]
    turns = [{"turn": 2, "active_player": A, "events": [
        cast(A, "Grave Whisper"), res("Grave Whisper (52) - Search your library."),
        cast(A, "Deep Search"), res("Deep Search (51) - Search your library.")]}]
    agents = [
        AG(2, A, "search_seen", SS(1, "Graveyard", "-", "Rust Ring", "Grave Whisper")),
        AG(2, A, "tutor_steer", "sid=1 mode=plan value=7 stockValue=5 steer=Big Finish over=Rust Ring"),
        AG(2, A, "search_seen", SS(2, "Graveyard", "-", "Rust Ring", "Grave Whisper")),
        AG(2, A, "tutor_steer", "sid=2 mode=plan value=7 stockValue=5 steer=Rot Titan over=Rust Ring"),
        AG(2, A, "tutor_cast", "Deep Search seeking Tide Oracle reach=false"),
        AG(2, A, "search_seen", SS(3, "Hand", "Tide Oracle", "Final Portal", "Deep Search")),
        AG(2, A, "tutor_steer", "sid=3 mode=plan value=5 stockValue=9 steer=Rust Ring over=Final Portal"),
    ]
    return {"players": [A, B], "turns": turns, "zones": zones, "agent_events": agents,
            "result": {"winner": A, "draw": False}}


def result():
    return {"meta": {"agent": "simlab-forge-shim/0.16.0", "agents": ["plan", "stock"]},
            "games": [game0(), game1()]}


def facts():
    return qctx.CardFacts(cache=copy.deepcopy(CACHE))


def reach(f):
    return Reach(searches=SEARCHES, types=TYPES, facts=f)


def run(plans=PLANS, res_=None):
    f = facts()
    ctx = qctx.from_result_dict(res_ or result(), source="synthetic", plans=copy.deepcopy(plans)
                                if plans is not None else None, facts=f, forge=None)
    return tutors.detect(ctx, reach=reach(f))


def eq(got, want, what):
    assert got == want, f"{what}: got {got!r}, want {want!r}"


# ------------------------------------------------------------------ tests --

def test_clause_verdicts():
    green_elf = {"tokens": {"Creature", "Elf"}, "cmc": 1.0, "colors": {"G"}, "power": 1}
    blue_wiz = {"tokens": {"Creature", "Wizard"}, "cmc": 2.0, "colors": {"U"}, "power": 1}
    rock = {"tokens": {"Artifact"}, "cmc": 3.0, "colors": set(), "power": None}
    king = {"tokens": {"Legendary", "Creature", "Human"}, "cmc": 4.0, "colors": {"W"}, "power": 3}
    spell2 = {"tokens": {"Instant"}, "cmc": 2.0, "colors": {"U"}, "power": None}
    goblin = {"tokens": {"Creature", "Goblin"}, "cmc": 1.0, "colors": {"R"}, "power": None}
    desert = {"tokens": {"Land", "Desert"}, "cmc": 0.0, "colors": set(), "power": None}
    eq(clause_verdict("Creature.Green+cmcLEX", green_elf), COND, "X-bound green creature")
    eq(clause_verdict("Creature.Green+cmcLEX", blue_wiz), False, "colour excludes")
    eq(clause_verdict("Creature.Green+cmcLEX", rock), False, "type excludes")
    eq(clause_verdict("Card.!Legendary", king), False, "negated supertype")
    eq(clause_verdict("Card.!Legendary", blue_wiz), True, "nonlegendary passes")
    eq(clause_verdict("Card.nonLegendary", king), False, "non- prefix")
    eq(clause_verdict("Instant.cmcLE2", spell2), True, "fixed MV cap")
    eq(clause_verdict("Sorcery.cmcLE2", spell2), False, "wrong spell type")
    eq(clause_verdict("Artifact.cmcEQ3", rock), True, "MV equals")
    eq(clause_verdict("Artifact.cmcEQ3", {**rock, "cmc": 2.0}), False, "MV differs")
    eq(clause_verdict("Creature.powerLE2", king), False, "power cap")
    eq(clause_verdict("Creature.powerLE2", goblin), COND, "unknown power")
    eq(clause_verdict("Permanent.Goblin", goblin), True, "permanent subtype")
    eq(clause_verdict("Permanent.Goblin", spell2), False, "not a permanent")
    eq(clause_verdict("Card.Creature+Green+nonLegendary+cmcLE3", green_elf), True, "stacked quals")
    eq(clause_verdict("Desert", desert), True, "subtype base")
    eq(clause_verdict("Card.IsRemembered", rock), SKIP, "a chosen-card step is not a search")
    eq(clause_verdict("Remembered.sameName", rock), SKIP, "dynamic base")
    eq(clause_verdict("Card.sameCMC", rock, tutor_cmc=3.0), True, "transmute match")
    eq(clause_verdict("Card.sameCMC", rock, tutor_cmc=1.0), False, "transmute mismatch")
    eq(clause_verdict("Card.sameCMC", rock, tutor_cmc=None), COND, "transmute unknown")
    eq(clause_verdict("Creature.withFlashback", goblin), COND, "unknown property qualifier")
    eq(clause_verdict("Card.YouOwn", rock), True, "ownership is not a restriction")
    eq(combine_verdicts([False, SKIP, COND]), COND, "cond beats false")
    eq(combine_verdicts([False, True]), True, "any true")
    eq(combine_verdicts([SKIP]), None, "only non-type searches")


def test_parsers():
    tc = tutors.parse_tutor_cast("Worldly Seer seeking Felid Guard")
    eq((tc["tutor"], tc["want"], tc["reach"]), ("Worldly Seer", "Felid Guard", None), "0.16 detail")
    tc = tutors.parse_tutor_cast("Worldly Seer seeking Felid Guard, the Warden reach=false x=1")
    eq((tc["want"], tc["reach"]), ("Felid Guard, the Warden", False), "0.17 reach suffix")
    eq(tutors.parse_tutor_cast("A seeking B reach=true")["reach"], True, "reach true")
    ss = tutors.parse_search_seen(SS(4, "Graveyard", "Tide Oracle", "Rot Titan|Rust Ring", "Grave Whisper"))
    eq((ss["sid"], ss["dest"], ss["missing"], ss["picked"], ss["src"]),
       ("4", "Graveyard", "Tide Oracle", "Rot Titan|Rust Ring", "Grave Whisper"), "search_seen")
    st = tutors.parse_steer("sid=2 mode=plan value=8 stockValue=6 steer=Rust Ring over=Rot Titan")
    eq((st["sid"], st["steer"], st["over"]), ("2", "Rust Ring", "Rot Titan"), "steer")
    eq(tutors.primary_type("Creature,Artifact"), "Creature", "zone types are comma-joined")
    eq(tutors.primary_type("Artifact Creature \u2014 Golem"), "Creature", "type line")
    eq(tutors.primary_type(""), "Unknown", "no types")


def test_reach_helpers():
    r = reach(facts())
    eq(r.dest_kind("Top Seer"), "library_top", "library-top tutor")
    eq(r.dest_kind("Twin Omens"), "hand", "reveal-then-hand search counts as hand")
    eq(r.dest_kind("Grave Whisper"), "graveyard", "graveyard destination")
    eq(r.cast_mode("Mind Shuffle"), "keyword", "transmute")
    eq(r.cast_mode("Pod Engine"), "activated", "activated search")
    eq(r.cast_mode("Deep Search"), "spell", "spell")
    eq(r.cast_mode("Unknown Card"), None, "no search")
    eq(r.generic("Deep Search"), True, "generic")
    eq(r.generic("Scholar's Query"), False, "restricted")
    eq(r.restriction("Scholar's Query", "Tide Oracle")[0], False, "type excludes")
    eq(r.restriction("Verdant Call", "Tide Oracle")[0], COND, "X-bound")
    eq(r.restriction("Mind Shuffle", "Iron Idol")[0], True, "same MV")
    eq(r.restriction("Twin Omens", "Rot Titan")[0], True, "multi-step search reads its first step")
    eq(r.restriction("Nobody's Tutor", "Rot Titan")[0], None, "unknown tutor")
    eq(r.restriction("Deep Search", "Mystery Card")[0], None, "unknown target")
    assert r.nonland_tutor("Scholar's Query") and not r.nonland_tutor("Pod Engine"), "nonland tutor"


def test_detect_counts():
    m, flags = run()
    a = m["by_seat"]["Alpha"]["plan"]
    b = m["by_seat"]["Beta"]["stock"]
    eq(a["tutor_cast"], 5, "tutor_cast")
    eq(a["unreachable"], 3, "unreachable")
    eq(a["unreachable_reasons"], {"restriction": 1, "in_graveyard": 1, "shim_reach_false": 1},
       "reasons")
    eq(a["reach_basis"], {"forge_offer": 2, "index": 2, "shim": 1}, "basis")
    eq((a["restriction_excludes"], a["restriction_conditional"], a["restriction_unknown"]),
       (1, 1, 0), "restriction")
    eq(a["seeking_gy_exile"], 1, "piece already binned")
    eq((a["searched"], a["searched_not_offered"]), (3, 3), "searches")
    eq((a["x_resolved"], a["x_zero"]), (1, 1), "X")
    eq(a["failed_to_target"], 1, "failed to target")
    eq(a["cast_never_searches"], {"keyword": 1}, "transmute cast as a spell")
    eq((a["tutors_drawn"], a["tutor_spells_cast"], a["tutor_spells_cast_by_shim"]), (6, 6, 5),
       "guard counts (the commander is not a tutor drawn)")
    eq(a["casts_per_drawn"], 1.0, "guard")
    eq(a["phase"], {"hand": {"own_before_main2": 1, "own_main2_or_later": 1},
                    "battlefield": {"own_main2_or_later": 1},
                    "graveyard": {"own_before_main2": 2},
                    "keyword_only": {"own_before_main2": 1}}, "phase buckets")
    eq(a["pick_types"], {"Instant": 2, "Artifact": 2}, "pick types")
    eq((a["generic_picks"], a["generic_picks_creature"]), (1, 0), "generic picks")
    eq(a["fetch_use"], {"hand": {"fetched": 2, "used_same_turn": 1}}, "fetch use")
    eq((a["gy_searches"], a["gy_searches_picked"], a["gy_steers"]), (3, 3, 3), "gy searches")
    eq((a["gy_steers_no_use"], a["gy_steers_graveyard_use"], a["gy_steers_unknown"]), (1, 2, 0),
       "gy steer classes (heuristics)")
    eq(a["gy_steer_cards"]["no_use"], {"Rust Ring": 1}, "no-use cards")
    eq(a["gy_steer_cards"]["graveyard_use"], {"Big Finish": 1, "Rot Titan": 1}, "expected cards")
    eq((a["closer_seen"], a["closer_overrides"]), (1, 1), "closer override")
    eq(a["unreachable_rate"], 0.6, "rate")

    eq(b["tutor_cast"], 0, "stock seats make no tutor_cast")
    eq((b["tutors_drawn"], b["tutor_spells_cast"]), (2, 2), "stock guard counts")
    eq(b["phase"], {"library_top": {"opp_main2_or_later": 1}, "hand": {"own_main2_or_later": 1}},
       "stock phase")
    eq((b["library_top_before_main2_rate"], b["library_top_timely_rate"]), (0.0, 1.0),
       "an opponent's end step is timely but not before main 2")
    eq(b["pick_types"], {"Creature": 2}, "stock picks inferred from zones")
    eq((b["generic_picks"], b["generic_picks_creature"]), (1, 1), "stock generic pick")
    eq(b["fetch_use"], {"library_top": {"fetched": 1}, "hand": {"fetched": 1}}, "stock fetch use")

    eq(m["pooled"]["tutor_cast"], 5, "pooled")
    eq(m["pooled"]["tutors_drawn"], 8, "pooled guard")
    eq(set(m["by_pilot"]), {"plan", "stock"}, "pilots")
    eq(m["kind"], "rules", "detector kind")

    kinds = {}
    for f in flags:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
        assert set(f) == {"game", "turn", "player", "kind", "detail", "anchor"}, f
        assert set(f["anchor"]) == {"game", "turn", "player", "agent_event_index"}, f
        assert "\u2014" not in f["detail"], f"em dash in a flag detail: {f['detail']}"
    eq(kinds, {"tutor_unreachable": 3, "tutor_x_zero": 1, "tutor_failed_target": 1,
               "tutor_cast_never_searches": 1, "tutor_gy_steer_no_use": 1,
               "tutor_closer_override": 1}, "flag kinds")
    by = {(f["kind"], f["game"]): f for f in flags}
    eq(by[("tutor_x_zero", 0)]["anchor"],
       {"game": 0, "turn": 5, "player": A, "agent_event_index": 3}, "x anchor")
    eq(by[("tutor_gy_steer_no_use", 0)]["anchor"]["agent_event_index"], 6, "steer anchor")
    eq(by[("tutor_closer_override", 1)]["anchor"]["agent_event_index"], 6, "closer anchor")
    unreach0 = [f for f in flags if f["kind"] == "tutor_unreachable" and f["game"] == 0]
    assert any("limited to Instant,Sorcery" in f["detail"] for f in unreach0), unreach0
    assert any("already in the graveyard" in f["detail"] for f in unreach0), unreach0


def test_plan_v2_graveyard_targets():
    plans = copy.deepcopy(PLANS)
    plans["planVersion"] = 2
    plans["decks"]["Alpha"]["search"]["graveyardTargets"] = {"Rot Titan": 7, "Rust Ring": 0}
    m, _ = run(plans)
    a = m["by_seat"]["Alpha"]["plan"]
    eq((a["gy_steers_no_use"], a["gy_steers_graveyard_use"]), (2, 1),
       "plan data wins: Big Finish is not a listed target, a 0 is not a target")
    eq(a["gy_steer_cards"]["graveyard_use"], {"Rot Titan": 1}, "v2 expected")
    # A version-1 plan carrying the field is not trusted with it.
    plans1 = copy.deepcopy(plans)
    del plans1["planVersion"]
    m1, _ = run(plans1)
    eq(m1["by_seat"]["Alpha"]["plan"]["gy_steers_no_use"], 1, "v1 plan uses the heuristics")
    # A per-deck planVersion counts too.
    plans_deck = copy.deepcopy(plans1)
    plans_deck["decks"]["Alpha"]["planVersion"] = 2
    m2, _ = run(plans_deck)
    eq(m2["by_seat"]["Alpha"]["plan"]["gy_steers_no_use"], 2, "per-deck planVersion")


def test_without_plans():
    m, _ = run(plans=None)
    a = m["by_seat"]["Alpha"]["plan"]
    eq(a["tutor_cast"], 5, "reach does not need a plan")
    eq(a["unreachable"], 3, "same verdicts")
    eq(a["tutors_drawn"], 6, "fallback tutor set from the index")
    # No roles: no commander, no deck list; a steer onto an instant is then
    # judged on the card alone.
    eq(a["gy_steers_graveyard_use"], 0, "no commander text to lean on")


def test_combine():
    m, _ = run()
    c = tutors.combine([m, m])
    eq(c["pooled"]["tutor_cast"], 10, "summed")
    eq(c["pooled"]["unreachable_rate"], 0.6, "rate recomputed, not summed")
    eq(c["by_seat"]["Alpha"]["plan"]["gy_steer_cards"]["no_use"], {"Rust Ring": 2}, "nested sum")
    eq(c["by_pilot"]["stock"]["casts_per_drawn"], 1.0, "pilot ratio")


def test_rotated_pilots_and_plans_lookup():
    r = result()
    r["meta"] = {"rotations_detail": [{"agents": ["plan", "stock"]}, {"agents": ["stock", "plan"]}],
                 "games_per_rotation_played": [1, 1]}
    ctx = qctx.from_result_dict(r, facts=facts(), forge=None)
    eq((ctx.pilot(0, A), ctx.pilot(0, B), ctx.pilot(1, A), ctx.pilot(1, B)),
       ("plan", "stock", "stock", "plan"), "per-rotation agents, positional by seat")
    eq(qctx.strip_seat("Ai(3)-Kess, Dissident"), "Kess, Dissident", "strip seat")
    eq(qctx.plan_version({}, {"planVersion": "2"}), 2, "file version")
    eq(qctx.plan_version({"planVersion": 3}, {"planVersion": 2}), 3, "deck version wins")
    eq(qctx.plan_version(None, None), 1, "default version")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "sim_20260101_000000_abc123_rotated.json").write_text("{}", encoding="utf-8")
        (d / "plans_20260101_000000_abc123.json").write_text("{}", encoding="utf-8")
        (d / "plans_20260101_000000_zzz999.json").write_text("{}", encoding="utf-8")
        eq(qctx.find_plans(d / "sim_20260101_000000_abc123_rotated.json").name,
           "plans_20260101_000000_abc123.json", "production naming")
        s = d / "study"
        s.mkdir()
        (s / "cell_POD1_rot0.jsonl").write_text("", encoding="utf-8")
        (s / "plans_POD1.json").write_text("{}", encoding="utf-8")
        (s / "plans_POD2.json").write_text("{}", encoding="utf-8")
        eq(qctx.find_plans(s / "cell_POD1_rot0.jsonl").name, "plans_POD1.json", "study naming")
        (s / "other.jsonl").write_text("", encoding="utf-8")
        eq(qctx.find_plans(s / "other.jsonl"), None, "no match among several plans")
        # A pod name matches a whole "_" part of the run's name, never a
        # substring: plans_a.json is not every run whose name holds an "a".
        t = d / "tokens"
        t.mkdir()
        (t / "plans_a.json").write_text("{}", encoding="utf-8")
        (t / "plans_b.json").write_text("{}", encoding="utf-8")
        eq(qctx.find_plans(t / "cell_banana_rot0.jsonl"), None, "no substring match")
        eq(qctx.find_plans(t / "cell_a_rot0.jsonl").name, "plans_a.json", "whole-part match")
        # One plans file in a directory is a study run's, but never another
        # production run's: a run-id result takes its own plans or none.
        o = d / "sim_results"
        o.mkdir()
        (o / "plans_20260101_000000_abc123.json").write_text("{}", encoding="utf-8")
        eq(qctx.find_plans(o / "sim_20260102_000000_def456_rotated.json"), None,
           "another run's plans are not this run's")
        eq(qctx.find_plans(o / "sim_20260101_000000_abc123.json").name,
           "plans_20260101_000000_abc123.json", "its own plans still found")
        eq(qctx.find_plans(o / "cell_POD1_rot0.jsonl").name,
           "plans_20260101_000000_abc123.json", "a study cell keeps the one-file fallback")


def test_from_jsonl():
    recs = [
        {"rec": "meta", "shim": "0.16.0", "agents": ["plan", "stock"], "players": [A, B]},
        {"rec": "entry", "game": 0, "seq": 1, "type": "TURN", "message": f"Turn 1 ({A})"},
        {"rec": "entry", "game": 0, "seq": 2, "type": "STACK_ADD", "message": f"{A} cast Verdant Call",
         "card": "Verdant Call", "cardId": 12},
        {"rec": "entry", "game": 0, "seq": 3, "type": "STACK_RESOLVE",
         "message": "Verdant Call (12) - Search your library for a creature card. (X=0)",
         "card": "Verdant Call", "cardId": 12},
        {"rec": "entry", "game": 0, "seq": 4, "type": "TURN", "message": f"Turn 2 ({B})"},
        {"rec": "zone", "game": 0, "turn": 0, "phase": "", "card": "Verdant Call", "cardId": 12,
         "from": "Library", "to": "Hand", "fromPlayer": A, "toPlayer": A, "types": "Sorcery",
         "pt": "", "token": False},
        {"rec": "zone", "game": 0, "turn": 1, "phase": "MAIN1", "card": "Verdant Call", "cardId": 12,
         "from": "Hand", "to": "Stack", "fromPlayer": A, "toPlayer": "", "types": "Sorcery",
         "pt": "", "token": False},
        {"rec": "agent", "game": 0, "turn": 1, "player": A, "event": "tutor_cast",
         "detail": "Verdant Call seeking Tide Oracle"},
        {"rec": "result", "game": 0, "draw": False, "winner": B, "turns": 2, "timedOut": False,
         "turnCapped": False, "ms": 10},
    ]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cell_POD9_rot0.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
        f = facts()
        ctx = qctx.from_path(p, facts=f, forge=None)
        eq(len(ctx.games), 1, "one game")
        eq(ctx.pilot(0, A), "plan", "meta.agents positional")
        eq(ctx.games[0].active.get(1), A, "active player from the log")
        m, flags = tutors.detect(ctx, reach=reach(f))
        a = m["by_seat"]["Alpha"]["plan"]
        eq((a["tutor_cast"], a["x_zero"], a["tutors_drawn"]), (1, 1, 1), "raw JSONL path")
        eq([x["kind"] for x in flags], ["tutor_x_zero"], "flags from raw JSONL")
        eq(m["basis"]["raw_jsonl"], 1, "basis records the raw file")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"{len(tests)} tests")
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
