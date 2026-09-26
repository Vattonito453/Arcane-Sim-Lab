import json, sys, collections
def winf(fs): return any(("Win the game" in f) or ("damage" in f) or ("lifeloss" in f) for f in fs)
B = collections.Counter(); M = collections.Counter()
for path in sys.argv[1:]:
    out = json.load(open(path, encoding="utf-8"))
    for pod, P in out.items():
        gm = {g["n"]: g for g in P["games"]}
        for name, combos in P["decks"].items():
            seen = set()
            for c in combos:
                key = tuple(sorted(c["cards"]))
                if key in seen: continue
                seen.add(key)
                if c["reading"] != "fired" or winf(c["produces"]): continue
                for g in c["games"]:
                    if not g["won"]: continue
                    gap = gm[g["n"]]["ended_turn"] - g["assembled_turn"]
                    B["gap0" if gap == 0 else "gap1-3" if gap < 4 else "gap4+ (>=1 round later)"] += 1
                    M[gm[g["n"]]["method"]] += 1
print(dict(B)); print(dict(M))
