import sys, glob, json, collections
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos
feat = collections.Counter()
cache = json.load(open(sys.argv[1], encoding="utf-8"))
for k, v in cache.items():
    for c in v.get("included", []):
        for f in c["produces"]:
            feat[f] += 1
for f, n in feat.most_common(80): print(n, f)
print(len(cache), "decks cached")
