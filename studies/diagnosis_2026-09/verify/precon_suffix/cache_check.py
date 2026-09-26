import json, sys, re
from pathlib import Path
ROOT = Path(r"C:/Users/Vatto/Magic Rules Engine")
sys.path.insert(0, str(ROOT/"engine"))
import combos
cache = json.loads((ROOT/"engine/combo_cache.json").read_text(encoding="utf-8"))
print("cache entries", len(cache))
cohort = json.loads((ROOT/"studies/precon_predict/cohort.json").read_text(encoding="utf-8"))
rows=[]
n_suffixed_decks=0; hits=0; empty=0; nonempty=[]; idents={}
clean_hits=0
for c in cohort:
    text = Path(c["file"]).read_text(encoding="utf-8")
    main, cmd = combos.parse_dck(text)
    nsuf = sum(1 for n,_ in main if "|" in n) + sum(1 for n in cmd if "|" in n)
    tot = len(main)+len(cmd)
    if nsuf: n_suffixed_decks+=1
    k = combos._key(main, cmd)
    # clean key
    cm = [(n.split("|")[0].strip(), q) for n,q in main]; cc=[n.split("|")[0].strip() for n in cmd]
    kc = combos._key(cm, cc)
    if kc in cache: clean_hits+=1
    if k in cache:
        hits+=1
        e = cache[k]
        ni, na = len(e["included"]), len(e["almost_included"])
        idents[e.get("identity")] = idents.get(e.get("identity"),0)+1
        if ni==0 and na==0: empty+=1
        else: nonempty.append((c["name"], ni, na, nsuf, tot, e.get("identity")))
        rows.append((c["name"], nsuf, tot, ni, na, e.get("identity")))
    else:
        rows.append((c["name"], nsuf, tot, None, None, None))
print("decks with any suffixed line:", n_suffixed_decks, "/", len(cohort))
print("suffixed-key cache hits:", hits, " empty:", empty, " identities:", idents)
print("nonempty:", nonempty)
print("clean-key cache hits:", clean_hits)
full = [r for r in rows if r[1]==r[2]]
print("fully suffixed decks:", len(full))
partial = [r for r in rows if 0<r[1]<r[2]]
print("partially suffixed:", partial)
nosuf = [r for r in rows if r[1]==0]
print("no-suffix decks:", nosuf)
