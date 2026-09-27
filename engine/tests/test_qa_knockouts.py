#!/usr/bin/env python3
"""qa.knockouts: every knockout dated by its lethal event, with cause, killer
and round; the turning point; and the consumers that read them
(analysis.win_method, scorecard._death_rounds). Synthetic fixtures only: no
Forge, no network, no user data.

Run: py engine/tests/test_qa_knockouts.py   ->  ALL ASSERTIONS PASSED
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

# Keep the card cache reads away from the tracked cache file.
os.environ.setdefault("MTG_DATA_DIR", tempfile.mkdtemp(prefix="qa_ko_"))

from qa import knockouts as K  # noqa: E402
import analysis  # noqa: E402
import scorecard  # noqa: E402

A, B, C, D = ("Ai(1)-Kess, Reanimator", "Ai(2)-Skrat's Revenge",
              "Ai(3)-Stella Lee, Wild Card", "Ai(4)-Krenko Goblins")
PHASES = ("Untap step", "Upkeep step", "Draw step", "Main phase, precombat")


def _possessive(p: str) -> str:
    return p + ("' " if p.endswith("s") else "'s ")


def game(turns, winner=None, zones=None, players=(A, B, C, D), draw=False,
         outcome=None):
    """turns: [(active, [(action, raw), ...]), ...]. Phase lines for the
    first four steps are added to every turn, before its events. `outcome`
    lines go on the last turn, as Forge prints them."""
    seq = 0
    out = []
    for i, (active, evs) in enumerate(turns):
        events = []
        for ph in PHASES:
            seq += 1
            events.append({"seq": seq, "action": "phase", "raw": _possessive(active) + ph})
        for action, raw in evs:
            seq += 1
            events.append({"seq": seq, "action": action, "raw": raw})
        out.append({"turn": i + 1, "active_player": active, "events": events})
    for raw in outcome or []:
        seq += 1
        out[-1]["events"].append({"seq": seq, "action": "game_outcome", "raw": raw})
    g = {"players": list(players), "turns": out,
         "result": {"winner": None if draw else winner, "draw": draw}}
    if zones is not None:
        g["zones"] = zones
    return g


def zone(turn, card, cid, frm, to, player, types="Creature", pt="4/4",
         token=False, phase="MAIN1"):
    return {"turn": turn, "phase": phase, "card": card, "cardId": cid,
            "from": frm, "to": to, "fromPlayer": player if frm != "None" else "",
            "toPlayer": player, "types": types, "pt": pt, "token": token}


def lost(p, why="because life total reached 0"):
    return f"{p} has lost {why}"


def won(p, why="because all opponents have lost"):
    return f"{p} has won {why}"


# --- the playtester's game 1, in miniature -----------------------------------
# Skrat's Revenge (B) poisons Stella (C) and Krenko (D) on its 2nd turn, the
# table skips them, and B finishes Kess (A) in combat on its 3rd turn. Forge
# prints the four outcome lines at game end, Kess first.

def game_one(with_zones=True):
    turns = [
        (A, []),
        (B, [("stack_add", f"{B} cast Beast Call"),
             ("stack_resolve", "Beast Call (50) - For each creature your opponents "
                               "control, create a 4/4 green Phyrexian Beast creature token.")]),
        (C, []),
        (D, []),
        (A, []),
        (B, [("stack_add", f"{B} cast Triumph of the Hordes"),
             ("stack_resolve", "Triumph of the Hordes (111) - Until end of turn, creatures "
                               "you control get +1/+1 and gain trample and infect."),
             ("combat", f"{B} assigned Phyrexian Beast Token (975) to attack {C}."),
             ("combat", f"{B} assigned Phyrexian Beast Token (997) to attack {D}."),
             ("damage", f"Phyrexian Beast Token (975) deals 10 combat damage to "
                        f"{C}(as poison counters)."),
             ("damage", f"Phyrexian Beast Token (997) deals 10 combat damage to "
                        f"{D}(as poison counters)."),
             ("damage", f"{D} receives 10 poison counter from {B}"),
             ("damage", f"{C} receives 10 poison counter from {B}")]),
        (A, []),
        (B, [("combat", f"{B} assigned Phyrexian Beast Token (975), Squirrel Token (1030) "
                        f"to attack {A}."),
             ("damage", f"Phyrexian Beast Token (975) deals 5 combat damage to {A}."),
             ("damage", f"Squirrel Token (1030) deals 1 combat damage to {A}."),
             ("life_change", f"Life: {A} 6 > 0")]),
    ]
    zones = None
    if with_zones:
        zones = [zone(2, "Phyrexian Beast Token", 975, "None", "Battlefield", B, token=True),
                 zone(2, "Phyrexian Beast Token", 997, "None", "Battlefield", B, token=True),
                 zone(2, "Squirrel Token", 1030, "None", "Battlefield", B, pt="1/1", token=True)]
    return game(turns, winner=B, zones=zones, outcome=[
        lost(A), won(B), lost(C, "because of obtaining 10 poison counters"),
        lost(D, "because of obtaining 10 poison counters")])


def test_game_one_reading():
    kos = K.knockouts(game_one())
    assert [k["player"] for k in kos] == [D, C, A], [k["player"] for k in kos]
    d, c, a = kos
    for k in (c, d):
        assert k["cause"] == "poison", k
        assert k["turn"] == 6 and k["round"] == 2, k
        assert k["by"] == B and k["basis"] == "zones", k
        assert k["card"] == "Phyrexian Beast Token", k
        assert k["dated_by"] == "event", k
        # Forge's damage line names only the token; the spell that gave it
        # infect is carried as log context.
        assert k["cast_before"] == ["Triumph of the Hordes"], k
    assert a["cause"] == "combat_damage" and a["turn"] == 8 and a["round"] == 3, a
    assert a["by"] == B and a["amount"] == 6, a
    # The card is the source that dealt the most, not the last line.
    assert a["card"] == "Phyrexian Beast Token", a
    # Dated by events, never by the loss lines Forge printed at game end.
    last_seq = max(e["seq"] for t in game_one()["turns"] for e in t["events"])
    assert all(k["seq"] < last_seq - 3 for k in kos), kos


def test_game_one_without_zones_uses_the_log():
    kos = K.knockouts(game_one(with_zones=False))
    by_player = {k["player"]: k for k in kos}
    # Poison: Forge's own "receives N poison counter from P"; combat: the
    # attack declaration that named the card.
    assert by_player[C]["by"] == B and by_player[C]["basis"] == "log", by_player[C]
    assert by_player[A]["by"] == B and by_player[A]["basis"] == "log", by_player[A]


def test_win_method_is_the_final_knockout():
    g = game_one()
    wm = analysis.win_method(g)
    assert wm == {"method": "combat damage", "detail": "Phyrexian Beast Token"}, wm
    # The v5 reading took the last-printed loss line and said poison.
    assert analysis._method_from_loss_lines(g)["method"] == "poison"


def test_death_rounds_from_knockouts():
    rounds = scorecard._death_rounds(game_one())
    assert rounds == {"Stella Lee, Wild Card": 2, "Krenko Goblins": 2,
                      "Kess, Reanimator": 3}, rounds
    sc = scorecard.scorecards({"games": [game_one()]})
    by = {d["deck"]: d for d in sc["decks"]}
    assert by["Krenko Goblins"]["medianDeathRound"] == 2
    assert by["Skrat's Revenge"]["methods"] == {"combat damage": 1}, by["Skrat's Revenge"]


# --- life-total causes --------------------------------------------------------

def two_player(evs_b_turn, outcome_reason="because life total reached 0", zones=None):
    return game([(A, []), (B, []), (A, evs_b_turn)], winner=A, players=(A, B),
                zones=zones, outcome=[won(A), lost(B, outcome_reason)])


def test_drain_is_life_loss_attributed_to_the_trigger_source():
    g = two_player([
        ("stack_add", f"{A} triggered Blood Artist targeting [{B}]"),
        ("life_change", f"Life: {B} 1 > 0"),
        ("life_change", f"Life: {A} 20 > 21"),
        ("stack_resolve", "Whenever Blood Artist or another creature dies, target player "
                          f"loses 1 life and you gain 1 life. (Targeting: [[{B}]]) "
                          "[Zone Changer: Goblin Token (514)]"),
    ])
    (k,) = K.knockouts(g)
    assert k["cause"] == "life_loss", k
    # The resolution's tag names the creature that died; the source and its
    # controller come from the paired stack line.
    assert k["card"] == "Blood Artist" and k["by"] == A, k
    assert analysis.win_method(g)["method"] == "life loss"


def test_noncombat_damage():
    g = two_player([
        ("stack_add", f"{A} cast Fireball targeting [{B}]"),
        ("damage", f"Fireball (55) deals 20 damage to {B}."),
        ("life_change", f"Life: {B} 20 > 0"),
        ("stack_resolve", f"Fireball (55) - Fireball (55) deals 20 damage to {B}."),
    ])
    (k,) = K.knockouts(g)
    assert k["cause"] == "noncombat_damage" and k["card"] == "Fireball", k
    assert k["by"] == A, k
    # Older Forge wording says "non-combat" outright.
    g2 = two_player([("damage", f"Rolling Earthquake (375) deals 20 non-combat damage to {B}."),
                     ("life_change", f"Life: {B} 20 > 0")])
    assert K.knockouts(g2)[0]["cause"] == "noncombat_damage"
    assert analysis.win_method(g2)["method"] == "non-combat damage"


def test_mixed_group_goes_to_the_larger_share_and_a_gain_does_not_split_it():
    g = two_player([
        ("damage", f"Zombie Token (430) deals 2 combat damage to {B}."),
        ("damage", f"Zombie Token (431) deals 2 combat damage to {B}."),
        ("damage", f"Impact Tremors (9) deals 1 non-combat damage to {B}."),
        ("life_change", f"Life: {B} 3 > 6"),     # a gain between damage and loss
        ("life_change", f"Life: {B} 6 > -1"),
    ])
    (k,) = K.knockouts(g)
    assert k["cause"] == "combat_damage" and k["card"] == "Zombie Token", k
    assert k["amount"] == 7, k


def test_life_total_with_no_life_line():
    g = two_player([], outcome_reason="because life total reached 0")
    (k,) = K.knockouts(g)
    assert k["cause"] == "life_total" and k["dated_by"] == "turn_order", k
    assert k["seq"] is None, k
    assert analysis.win_method(g)["method"] == "combat damage / life loss"


# --- commander damage, alternate wins, lose effects, unknowns ------------------

def test_commander_damage_prefers_the_commander():
    turns = [
        (A, [("damage", f"Kilo, Apogee Mind (100) deals 11 combat damage to {B}."),
             ("life_change", f"Life: {B} 60 > 49")]),
        (B, []),
        (A, [("damage", f"Kilo, Apogee Mind (100) deals 10 combat damage to {B}."),
             ("damage", f"Huge Beast (300) deals 22 combat damage to {B}."),
             ("life_change", f"Life: {B} 49 > 17")]),
    ]
    zones = [zone(0, "Kilo, Apogee Mind", 100, "None", "Command", A, phase=""),
             zone(1, "Kilo, Apogee Mind", 100, "Command", "Stack", A)]
    g = game(turns, winner=A, players=(A, B), zones=zones, outcome=[
        won(A), lost(B, "due to accumulation of 21 damage from generals")])
    (k,) = K.knockouts(g)
    assert k["cause"] == "commander_damage", k
    assert k["card"] == "Kilo, Apogee Mind" and k["by"] == A and k["turn"] == 3, k
    assert analysis.win_method(g)["method"] == "commander damage"


def test_alt_win_dates_every_loser_to_the_winning_spell():
    turns = [(A, []), (B, []), (C, []),
             (A, [("stack_add", f"{A} cast Thassa's Oracle"),
                  ("stack_resolve", "Thassa's Oracle (7) - Creature 1 / 3"),
                  ("stack_add", f"{A} triggered Thassa's Oracle"),
                  ("stack_resolve", "When Thassa's Oracle enters, look at the top X cards "
                                    "[Zone Changer: Thassa's Oracle (7)]")])]
    spell = "because an opponent has won by spell 'Thassa's Oracle'"
    g = game(turns, winner=A, players=(A, B, C),
             outcome=[won(A, "due to effect of 'Thassa's Oracle'"), lost(B, spell),
                      lost(C, spell)])
    kos = K.knockouts(g)
    assert [k["cause"] for k in kos] == ["alt_win", "alt_win"], kos
    assert len({k["seq"] for k in kos}) == 1, kos
    assert all(k["by"] == A and k["card"] == "Thassa's Oracle" for k in kos), kos
    assert analysis.win_method(g) == {"method": "spell", "detail": "Thassa's Oracle"}


def test_lose_effect():
    turns = [(A, [("stack_add", f"{A} cast Summoner's Pact")]), (B, []),
             (A, [("stack_add", f"{A} triggered Summoner's Pact"),
                  ("stack_resolve", "At the beginning of your next upkeep, pay {2}{G}{G}. "
                                    "If you don't, you lose the game. [Card: Summoner's "
                                    f"Pact (40), Activator: {A}]")])]
    g = game(turns, winner=B, players=(A, B), outcome=[
        lost(A, "due to effect of spell 'Summoner's Pact'"), won(B)])
    (k,) = K.knockouts(g)
    assert k["cause"] == "lose_effect" and k["card"] == "Summoner's Pact", k
    assert k["by"] == A and k["turn"] == 3, k


PACT = "Pact of Negation"
PACT_LOSS = f"due to effect of spell '{PACT}'"


def pact_pod(with_zones: bool):
    """A and C each fail to pay for their own Pact of Negation; C casts its
    Pact (and triggers it) inside A's window, after A's own trigger. The
    shim's real logs print the unpaid trigger's stack line and no resolution
    (the player is gone), as on turn 4 here."""
    turns = [
        (A, []),
        (B, [("stack_add", f"{A} cast {PACT} targeting [Wrath of God]"),
             ("stack_resolve", f"{PACT} (40) - Counter Wrath of God (7). At the beginning "
                               "of your next upkeep, pay {3}{U}{U}. If you don't, you lose "
                               "the game.")]),
        (C, []),
        (A, [("stack_add", f"{A} triggered {PACT}")]),
        (B, [("stack_add", f"{C} cast {PACT} targeting [Fireball]"),
             ("stack_resolve", f"{PACT} (61) - Counter Fireball (9). At the beginning of "
                               "your next upkeep, pay {3}{U}{U}. If you don't, you lose "
                               "the game.")]),
        (C, [("stack_add", f"{C} triggered {PACT}")]),
        (B, []),
    ]
    zones = None
    if with_zones:
        zones = [zone(2, PACT, 40, "Hand", "Stack", A, types="Instant", pt=""),
                 zone(5, PACT, 61, "Hand", "Stack", C, types="Instant", pt="")]
    return game(turns, winner=B, players=(A, B, C), zones=zones,
                outcome=[lost(A, PACT_LOSS), won(B), lost(C, PACT_LOSS)])


def test_lose_effect_is_dated_by_the_losers_own_line():
    # Reviewer-reported: an opponent's later cast or trigger of the same card
    # inside the loser's window used to date the knockout (a turn late) and
    # name that opponent as `by`.
    for with_zones in (False, True):
        g = pact_pod(with_zones)
        own_seq = next(e["seq"] for e in g["turns"][3]["events"]
                       if e["raw"] == f"{A} triggered {PACT}")
        c_seq = next(e["seq"] for e in g["turns"][5]["events"]
                     if e["raw"] == f"{C} triggered {PACT}")
        kos = K.knockouts(g)
        assert [k["player"] for k in kos] == [A, C], kos
        a, c = kos
        assert a["cause"] == "lose_effect" and a["card"] == PACT, a
        assert a["seq"] == own_seq and a["turn"] == 4 and a["by"] == A, (with_zones, a)
        assert a["dated_by"] == "event", a
        assert c["seq"] == c_seq and c["turn"] == 6 and c["by"] == C, (with_zones, c)
        rounds = scorecard._death_rounds(g)
        assert rounds == {scorecard.bare(A): 2, scorecard.bare(C): 2}, rounds
        assert analysis.win_method(g)["method"] == "lose-the-game effect"


def test_lose_effect_from_another_players_card_falls_back_to_any_line():
    # "Target player loses the game": the loser has no line of their own for
    # the card, so the caster's line dates it and names the caster.
    door = "Door to Nothingness"
    g = two_player([
        ("stack_add", f"{A} activated {door} targeting [{B}]"),
        ("stack_resolve", f"{door} (12) - Target player loses the game. "
                          f"(Targeting: [[{B}]])"),
    ], outcome_reason=f"due to effect of spell '{door}'")
    (k,) = K.knockouts(g)
    assert k["cause"] == "lose_effect" and k["card"] == door, k
    assert k["by"] == A and k["turn"] == 3 and k["dated_by"] == "event", k


def test_unknown_reason_is_flagged_and_undated():
    g = two_player([], outcome_reason="because of a rule nobody has seen")
    metrics, flags = K.detect(g_result := {"games": [g]})
    assert metrics["by_cause"] == {"unknown": 1}, metrics
    kinds = sorted(f["kind"] for f in flags)
    assert kinds == ["unclassified_loss", "undated_knockout"], flags
    assert analysis.win_method(g)["method"] == "other"
    assert g_result["games"][0] is g


# --- deck-outs ---------------------------------------------------------------

DECK = "trying to draw cards from empty library"


def test_deckout_dated_by_the_failed_draw_on_stdout():
    # A's last own turn is 4; it drew (and failed) in that draw step.
    g = game([(A, []), (B, []), (C, []), (A, []), (B, [])], winner=B, players=(A, B, C),
             outcome=[lost(A, DECK), won(B), lost(C)])
    g["turns"][4]["events"].append({"seq": 999, "action": "life_change",
                                    "raw": f"Life: {C} 3 > 0"})
    kos = K.knockouts(g)
    a = [k for k in kos if k["player"] == A][0]
    assert a["cause"] == "deckout" and a["turn"] == 4 and a["dated_by"] == "event", a
    assert a["by"] is None and a["basis"] == "log", a
    assert analysis._method_from_loss_lines(g)["method"] != "deckout"  # v5 could not see it


def test_deckout_uses_the_zone_stream_for_when_the_library_emptied():
    # Library emptied in A's main phase on turn 1 (a Consultation), so A's
    # draw step that turn was a success and the NEXT draw step, turn 3, failed.
    zones = [zone(1, "Island", 5, "Library", "Exile", A, types="Land", pt="",
                  phase="MAIN1")]
    g = game([(A, []), (B, []), (A, []), (B, [])], winner=B, players=(A, B), zones=zones,
             outcome=[lost(A, DECK), won(B)])
    (k,) = K.knockouts(g)
    assert k["cause"] == "deckout" and k["turn"] == 3, k
    assert k["basis"] == "zones", k
    assert k["library_emptied"] == {"turn": 1, "phase": "MAIN1"}, k
    assert analysis.win_method(g)["method"] == "deckout"
    metrics, flags = K.detect({"games": [g]})
    assert [f["kind"] for f in flags] == ["deckout"], flags


# --- windows and names -------------------------------------------------------

def test_extra_turn_does_not_close_the_window():
    # C's last own turn is index 2. A then takes an extra turn (A, A): the
    # distance from C's seat repeats and must not read as a wrap.
    turns = [(A, []), (B, []), (C, []), (A, []), (A, []),
             (B, [("damage", f"Bear (3) deals 9 combat damage to {C}."),
                  ("life_change", f"Life: {C} 9 > 0")])]
    g = game(turns, winner=B, players=(A, B, C),
             outcome=[lost(A), won(B), lost(C)])
    g["turns"][5]["events"].append({"seq": 998, "action": "life_change",
                                    "raw": f"Life: {A} 1 > 0"})
    ctx = K._Ctx(g)
    assert K._window(ctx, K._turn_order(ctx), C) == (2, 6), K._window(ctx, K._turn_order(ctx), C)
    c = [k for k in K.knockouts(g) if k["player"] == C][0]
    assert c["turn"] == 6 and c["dated_by"] == "event", c


def test_window_closes_when_the_table_passes_the_seat():
    g = game_one()
    ctx = K._Ctx(g)
    order = K._turn_order(ctx)
    # Stella's last own turn is index 2; the table passes her seat at index 6
    # (A's third turn comes straight after B's second).
    assert K._window(ctx, order, C) == (2, 6), K._window(ctx, order, C)
    assert K._window(ctx, order, A) == (6, 8), K._window(ctx, order, A)


def test_truncated_legacy_player_keys():
    # Result files from 2026-07-22 carry player keys cut to "Ai(1"; the names
    # come from the outcome lines instead.
    g = two_player([("damage", f"Bear (3) deals 20 combat damage to {B}."),
                    ("life_change", f"Life: {B} 20 > 0")])
    g["players"] = ["Ai(1", "Ai(2"]
    for t in g["turns"]:
        t["active_player"] = t["active_player"][:4]
    (k,) = K.knockouts(g)
    assert k["player"] == B and k["cause"] == "combat_damage", k


# --- turning point -----------------------------------------------------------

def test_turning_point_from_zones():
    zones = [
        zone(1, "Grizzly Bears", 1, "Hand", "Battlefield", A, pt="2/2"),     # early lone bear
        zone(2, "Hill Giant", 2, "Hand", "Battlefield", B, pt="3/3"),
        zone(3, "Ogre", 3, "Hand", "Battlefield", C, pt="3/3"),
        zone(5, "Wall", 4, "Hand", "Battlefield", A, pt="0/4"),
        zone(6, "Ogre", 5, "Hand", "Battlefield", C, pt="3/3"),
        # Turn 7 (C's): C wipes B's board and makes three 4/4 Beasts. C wins.
        zone(7, "Beast Token", 10, "None", "Battlefield", C, token=True),
        zone(7, "Beast Token", 11, "None", "Battlefield", C, token=True),
        zone(7, "Beast Token", 12, "None", "Battlefield", C, token=True),
        zone(7, "Hill Giant", 2, "Battlefield", "Graveyard", B, pt="3/3"),
    ]
    turns = [(A, []), (B, []), (C, []), (A, []), (B, []), (C, []),
             (C, [("stack_add", f"{C} cast Beast Uprising"),
                  ("damage", "Beast Token (10) deals 4 damage to Hill Giant (2)."),
                  ("damage", "Hill Giant (2) deals 3 damage to Beast Token (10)."),
                  ("stack_resolve", "Beast Uprising (70) - Create three 4/4 Beasts; one "
                                    "fights target creature."),
                  ("zone_change", "Hill Giant (2) was put into Graveyard from Battlefield.")]),
             (A, []), (B, []),
             (C, [("damage", f"Beast Token (10) deals 30 combat damage to {A}."),
                  ("life_change", f"Life: {A} 30 > 0"),
                  ("damage", f"Beast Token (11) deals 30 combat damage to {B}."),
                  ("life_change", f"Life: {B} 30 > 0")])]
    g = game(turns, winner=C, players=(A, B, C), zones=zones,
             outcome=[lost(A), lost(B), won(C)])
    tp = K.turning_point(g)
    assert tp is not None and tp["turn"] == 7, tp
    assert tp["basis"] == "zones" and tp["inferred"] is False, tp
    assert tp["seat"] == C and tp["event_hint"] == "Beast Uprising", tp
    assert tp["event_by"] == C, tp
    assert tp["share_after"] > tp["share_before"], tp
    assert tp["round"] == scorecard.true_round(g, 6), tp


def test_elimination_is_not_a_swing_and_draws_have_none():
    # B's board is big, then B is knocked out; the winner's share among the
    # seats still in does not move, so that turn must not be the turning point.
    zones = [zone(1, "Titan", 1, "Hand", "Battlefield", B, pt="9/9"),
             zone(2, "Bear", 2, "Hand", "Battlefield", A, pt="2/2"),
             zone(3, "Giant", 3, "Hand", "Battlefield", A, pt="4/4")]
    turns = [(B, []), (A, []), (A, [("damage", f"Giant (3) deals 20 combat damage to {B}."),
                                     ("life_change", f"Life: {B} 20 > 0")])]
    g = game(turns, winner=A, players=(A, B), zones=zones, outcome=[won(A), lost(B)])
    tp = K.turning_point(g)
    assert tp is not None and tp["turn"] == 2, tp
    g["result"] = {"winner": None, "draw": True}
    assert K.turning_point(g) is None


def test_turning_point_on_stdout_is_inferred():
    turns = [(A, [("stack_add", f"{A} cast Grizzly Bears"),
                  ("stack_resolve", "Grizzly Bears - Creature 2 / 2")]),
             (B, [("stack_add", f"{B} cast Krenko, Mob Boss"),
                  ("stack_resolve", "Krenko, Mob Boss - Creature 3 / 3"),
                  ("stack_add", f"{B} activated Krenko, Mob Boss"),
                  ("stack_resolve", f"Krenko, Mob Boss (401) - {B} creates ten 1/1 red "
                                    "Goblin creature tokens.")]),
             (A, [])]
    g = game(turns, winner=B, players=(A, B), outcome=[lost(A), won(B)])
    tp = K.turning_point(g)
    assert tp is not None and tp["turn"] == 2, tp
    assert tp["basis"] == "log" and tp["inferred"] is True, tp
    assert tp["event_hint"] == "Krenko, Mob Boss", tp


# --- detector contract and the analysis payload ------------------------------

def test_detect_accepts_the_shared_context_shapes():
    result = {"games": [game_one()]}

    class Ctx:
        pass
    obj = Ctx()
    obj.result = result
    for ctx in (result, {"result": result}, obj):
        metrics, flags = K.detect(ctx)
        assert metrics["games"] == 1 and metrics["knockouts"] == 3, metrics
        assert metrics["by_cause"] == {"poison": 2, "combat_damage": 1}, metrics
        assert metrics["turning_points"] == 1, metrics
        assert metrics["per_game"][0]["turning_point"]["event_hint"] is not None
        assert flags == [], flags
    json.dumps(metrics)  # serialisable, for qa.json


def test_analysis_payload_shape_is_additive():
    rep = analysis.analyse({"games": [game_one(), two_player([])], "meta": {"decks": []}},
                           deck_dirs=[], fetch=False)
    assert rep["version"] == 6, rep["version"]
    for g in rep["games"]:
        # The keys the results page and the scorecards already read ...
        for key in ("n", "winner", "ended_turn", "method", "detail"):
            assert key in g, (key, g)
        # ... plus the knockouts and the turning point.
        assert isinstance(g["knockouts"], list) and "turning_point" in g, g
    assert rep["summary"]["methods"] == {"combat damage": 1,
                                         "combat damage / life loss": 1}, rep["summary"]
    assert rep["summary"]["knockout_causes"] == {"poison": 2, "combat_damage": 1,
                                                 "life_total": 1}, rep["summary"]
    json.dumps(rep)


def test_draw_keeps_its_knockouts_but_reads_draw():
    g = game_one()
    g["result"] = {"winner": None, "draw": True, "timedOut": True}
    assert analysis.win_method(g)["method"] == "draw"
    rep = analysis.analyse({"games": [g], "meta": {"decks": []}}, deck_dirs=[], fetch=False)
    assert rep["games"][0]["method"] == "draw" and len(rep["games"][0]["knockouts"]) == 3


def test_a_broken_analyzer_falls_back_to_the_loss_lines():
    real = analysis.qa_knockouts.knockouts
    real_story = analysis.qa_knockouts.analyse_game

    def boom(*_a, **_k):
        raise RuntimeError("synthetic analyzer failure")
    analysis.qa_knockouts.knockouts = boom
    analysis.qa_knockouts.analyse_game = boom
    try:
        assert analysis.win_method(game_one())["method"] == "poison"
        rep = analysis.analyse({"games": [game_one()], "meta": {"decks": []}},
                               deck_dirs=[], fetch=False)
        assert rep["games"][0]["knockouts"] == [] and rep["games"][0]["method"] == "poison"
    finally:
        analysis.qa_knockouts.knockouts = real
        analysis.qa_knockouts.analyse_game = real_story


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
