import glob, sys, collections
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos
from remidx import load
idx = load()
def e(n): return idx.get(n) or (idx.get(n.split(" // ")[0]) if " // " in n else None)
kind = {}
decks_hit = set(); decks = set(); cls = collections.Counter()
for dck in sorted(glob.glob(r"C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks/*/dck/*.dck")):
    decks.add(dck)
    r = combos.combos_for_dck(dck, fetch=False); seen = set()
    for v in r["included"]:
        k = tuple(sorted(v["cards"]))
        if k in seen: continue
        seen.add(k)
        fl = [c for c in v["cards"] if e(c)["remAll"]]
        if not fl: cls["no flagged piece"] += 1; continue
        decks_hit.add(dck)
        def pk(c):
            x = e(c); nonmana = [a for a in x["ab"] if a != "Mana"]
            return "nonmana-activation" if nonmana else ("mana-only" if x["ab"] else "cast-only")
        ks = {pk(c) for c in fl}
        for c in fl: kind[c] = pk(c)
        cls["flagged: needs non-mana activation" if "nonmana-activation" in ks else ("flagged: mana ability only" if "mana-only" in ks else "flagged: cast-only (shim can cast)")] += 1
print("decks", len(decks), "decks with >=1 flagged line", len(decks_hit))
for k, v in cls.most_common(): print(v, k)
print(kind)
