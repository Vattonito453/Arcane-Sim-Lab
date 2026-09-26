import json, sys, os
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import analysis
for p in sys.argv[1:]:
    r = json.load(open(p, encoding="utf-8"))
    r.setdefault("file", os.path.basename(p))
    rep = analysis.analyse(r, fetch=False)
    gm = {g["n"]: g for g in rep["games"]}
    print("==", r["file"], "validity:", rep["validity"].get("quality"), rep["validity"].get("reasons"))
    for name, d in rep["decks"].items():
        for c in d["combos"]:
            print(" ", name, "|", " + ".join(c["cards"]), "| produces:", c["produces"][:5], "| reading", c["reading"])
            for g in c["games"]:
                if g["assembled_turn"] is not None:
                    G = gm[g["n"]]
                    print("     game", g["n"], "assembled T", g["assembled_turn"], "online", g["online_turns"], "won", g["won"],
                          "| game winner", G["winner"], "ended T", G["ended_turn"], "method", G["method"], "|", G["detail"][:80])
