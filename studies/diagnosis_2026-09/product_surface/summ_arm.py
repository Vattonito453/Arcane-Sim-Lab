import json, sys, collections
def winf(fs): return any(("Win the game" in f) or ("damage" in f) or ("lifeloss" in f) for f in fs)
tot = collections.Counter()
for path in sys.argv[1:]:
    out = json.load(open(path, encoding="utf-8"))
    for pod, P in out.items():
        gm = {g["n"]: g for g in P["games"]}
        for name, combos in P["decks"].items():
            for c in combos:
                tot["rows"] += 1
                tot["reading_"+c["reading"]] += 1
                conv = [g for g in c["games"] if g["won"]]
                if c["reading"] == "fired":
                    gaps = [gm[g["n"]]["ended_turn"] - g["assembled_turn"] for g in conv]
                    meths = collections.Counter(gm[g["n"]]["method"] for g in conv)
                    selfwin = winf(c["produces"])
                    tot["fired_selfwin" if selfwin else "fired_engine_only"] += 1
                    print(f"{path.split('/')[-1]} {pod} {name}: {' + '.join(c['cards'])} | selfwin={selfwin} conv={len(conv)}/{c['assembled_games']} methods={dict(meths)} turns_asm_to_win={gaps}")
                for g in c["games"]:
                    tot["assembled_game_rows"] += 1
                    if g["won"]: tot["converted_game_rows"] += 1
                    G = gm[g["n"]]
                    if G["method"] == "draw": tot["assembled_then_draw"] += 1
print(dict(tot))
