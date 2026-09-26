import json, sys
out = json.load(open(sys.argv[1], encoding="utf-8"))
for pod, P in out.items():
    gm = {g["n"]: g for g in P["games"]}
    print("==", pod, P["n_games"], "games; methods:", P["methods"])
    for name, combos in P["decks"].items():
        if not combos:
            print("  ", name, ": no combos"); continue
        for c in combos:
            win = any(("Win the game" in f) or ("damage" in f) or ("lifeloss" in f) for f in c["produces"])
            print(f"   {name}: {' + '.join(c['cards'])} | wins-by-itself={win} | assembled {c['assembled_games']}/{c['games_played']} conv {c['converted_games']} reading={c['reading']} idle={c['idle_online_turns']}")
            for g in c["games"]:
                G = gm[g["n"]]
                print(f"        g{g['n']} asmT{g['assembled_turn']} online{g['online_turns']} won={g['won']} | winner={G['winner']} endT{G['ended_turn']} method={G['method']} {G['detail'][:60]}")
