import json, glob, sys
from pathlib import Path
od = Path(__file__).parent
data = {}
for f in sorted(od.glob("out2_*.json")):
    d = json.load(open(f))
    data.update(d)

ROWS = [
    # (label, numerator, denominator)
    ("missed land drop / player-turn", "missed_land_drop", "player_turns"),
    ("ritual wasted / ritual cast", "ritual_wasted", "ritual_cast"),
    ("rituals wasted / seat-game", "ritual_wasted", "seat_games"),
    ("cleanup discards / seat-game", "cleanup_discard", "seat_games"),
    ("discarded castable permanent / seat-game", "cleanup_discard_castable_perm", "seat_games"),
    ("discarded line piece or tutor / seat-game", "cleanup_discard_line_or_tutor", "seat_games"),
    ("discarded spell, kept land, 6+ lands / seat-game", "cleanup_discard_spell_while_holding_land_6plus", "seat_games"),
    ("end step: castable perm unspent, no instant / turn", "unspent_castable_perm_no_instant", "tap_turns"),
    ("end step: castable perm unspent, instant held / turn", "unspent_castable_perm_hold_instant", "tap_turns"),
    ("end step: 4+ lands open, 2+cmc perm unspent, no instant / turn", "unspent4_castable_perm_no_instant", "tap_turns"),
    ("mean untapped lands at own end step", "untapped_at_end_sum", "tap_turns"),
    ("died holding castable instant answer / elimination", "died_holding_castable_answer", "elim_tap"),
    ("mean cards in hand at elimination", "hand_at_elim_sum", "eliminations"),
    ("attacker died for nothing / attacker", "attacker_died_for_nothing", "attackers"),
    ("  ... / blocked attacker", "attacker_died_for_nothing", "attackers_blocked"),
    ("  predictable from printed P/T / attacker", "attacker_died_for_nothing_predictable", "attackers"),
    ("blocked-attacker share", "attackers_blocked", "attackers"),
    ("chump when not needed / block made", "chump_not_needed", "rubric_blocks"),
    ("chump share of blocks (rubric v0)", "rubric_chumps", "rubric_blocks"),
    ("counter aimed at rock/ramp / counter cast", "counter_on_ramp_or_rock", "counters_cast"),
    ("removal on own permanent / targeted removal", "removal_on_own_permanent", "removal_targeted"),
    ("removal on <=2 power while 7+ power stands / targeted removal", "removal_small_target_while_7power_stands", "removal_targeted"),
    ("wrath while caster has biggest board / wrath", "wrath_while_ahead", "wraths"),
    ("wrath into <=1 enemy creature / wrath", "wrath_into_empty", "wraths"),
]
want = sys.argv[1:] or list(data)
for ds in want:
    n = data[ds]["n"]
    print("=" * 100)
    print(ds, "games", n.get("all|games"), "decided", n.get("all|decided"), "timedOut", n.get("all|timed_out"))
    pilots = sorted({k.split("|")[0] for k in n if not k.startswith("all")})
    print(f"{'':70s}" + "".join(f"{p:>16s}" for p in pilots))
    for lab, a, b in ROWS:
        cells = []
        for p in pilots:
            num = n.get(f"{p}|{a}", 0)
            den = n.get(f"{p}|{b}", 0)
            if den:
                v = num / den
                cells.append(f"{v:8.3f} ({num}/{den})" if den < 100000 else f"{v:.3f}")
            else:
                cells.append("       -")
        print(f"{lab:70s}" + "".join(f"{c:>16s}" for c in cells))
