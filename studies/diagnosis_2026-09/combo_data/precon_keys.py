import json, sys, re
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos
from pathlib import Path
cache = combos._load()
cohort = json.load(open(r"C:/Users/Vatto/Magic Rules Engine/studies/precon_predict/cohort.json"))
hit_raw = hit_clean = 0
zero_all = 0
suffixed = 0
for d in cohort:
    p = Path(d["file"])
    main, cmd = combos.parse_dck(p.read_text(encoding="utf-8"))
    if any("|" in n for n,_ in main): suffixed += 1
    k = combos._key(main, cmd)
    clean_main = [(n.split("|")[0], q) for n,q in main]
    clean_cmd = [n.split("|")[0] for n in cmd]
    kc = combos._key(clean_main, clean_cmd)
    if k in cache:
        hit_raw += 1
        e = cache[k]
        if not e["included"] and not e["almost_included"]:
            zero_all += 1
    if kc in cache: hit_clean += 1
print("cohort decks", len(cohort), "names with |SET suffix:", suffixed)
print("cache hits on raw (suffixed) key:", hit_raw, " of which zero included AND zero almost:", zero_all)
print("cache hits on clean key:", hit_clean)
# sample identity from one raw entry
for d in cohort[:3]:
    p = Path(d["file"]); main, cmd = combos.parse_dck(p.read_text(encoding="utf-8"))
    e = cache.get(combos._key(main, cmd)); print(d["name"], cmd, e and {k:(v if k=='identity' else len(v)) for k,v in e.items()})
