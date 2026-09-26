import json, glob, collections
from pathlib import Path
R = "C:/Users/Vatto/Magic Rules Engine/studies"
# deck name -> set of (frozenset cards, tuple produces), and per plan-file signature
lines = collections.defaultdict(dict)
sigs = collections.defaultdict(set)
for f in glob.glob(R + "/**/plans*.json", recursive=True):
    try: d = json.load(open(f, encoding="utf-8"))
    except Exception as e: continue
    decks = d.get("decks", d)
    for name, p in decks.items():
        if not isinstance(p, dict) or "lines" not in p: continue
        sig = tuple(sorted(tuple(sorted(l["cards"])) for l in p["lines"]))
        sigs[name].add((sig, len(p.get("search",{}).get("targets",{}))))
        for l in p["lines"]:
            lines[name][frozenset(l["cards"])] = tuple(l.get("produces", []))
print("decks with plans:", len(lines))
for n in sorted(sigs):
    if len(sigs[n]) > 1: print("VARIES", n, [(len(s[0]), s[1]) for s in sigs[n]])
prod = collections.Counter()
for n, ls in lines.items():
    for c, p in ls.items():
        for x in p: prod[x] += 1
json.dump({n: [[sorted(c), list(p)] for c, p in ls.items()] for n, ls in lines.items()}, open("lines_union.json", "w"), indent=0)
for x, c in prod.most_common(80): print(c, x)
