import glob, os, sys, collections
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import combos
from remidx import load
idx = load()
def rem(n):
    e = idx.get(n) or (idx.get(n.split(" // ")[0]) if " // " in n else None)
    return None if e is None else e["remAll"]
tot = 0; flagged = 0; uncached = 0; decks = 0; piece = collections.Counter(); missing = collections.Counter()
allu = {}  # global dedupe
for dck in sorted(glob.glob(r"C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks/*/dck/*.dck")):
    decks += 1
    r = combos.combos_for_dck(dck, fetch=False)
    if r is None: uncached += 1; continue
    seen = set()
    for v in r["included"]:
        k = tuple(sorted(v["cards"]))
        if k in seen: continue
        seen.add(k); tot += 1
        fl = [c for c in v["cards"] if rem(c)]
        for c in v["cards"]:
            if rem(c) is None: missing[c] += 1
        if fl: flagged += 1
        for c in fl: piece[c] += 1
        allu[k] = bool(fl)
print("decks", decks, "uncached", uncached, "lines (per-deck dedupe)", tot, "with remAll piece", flagged)
print("globally unique lines", len(allu), "with remAll piece", sum(allu.values()))
print(piece.most_common(25))
print("missing scripts", missing.most_common(10))
