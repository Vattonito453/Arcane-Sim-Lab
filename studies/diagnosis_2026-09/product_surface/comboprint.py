import sys
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos
for p in sys.argv[1:]:
    res = combos.combos_for_dck(p, fetch=False)
    print("==", p.split("decks")[-1], len(res["included"]))
    for c in res["included"]:
        print("  ", " + ".join(c["cards"]), "->", "; ".join(c["produces"][:4]), "| prereq:", c["prerequisites"][:120].replace("\n"," "))
