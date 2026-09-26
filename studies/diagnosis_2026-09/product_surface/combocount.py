import sys, glob, json, collections
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos
rows=[]
for p in sorted(glob.glob(r"C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks/*/dck/*.dck")):
    res = combos.combos_for_dck(p, fetch=False)
    if res is None:
        rows.append((p.split('decks')[-1], None, None, None)); continue
    inc = res["included"]
    win = [c for c in inc if any(("Win the game" in f) or ("Infinite damage" in f) or ("Lose the game" in f and "opponent" in f.lower()) or ("Each opponent loses" in f) for f in c["produces"])]
    rows.append((p.split('decks')[-1], len(inc), len(win), len(res["almost_included"])))
for r in rows: print(r)
