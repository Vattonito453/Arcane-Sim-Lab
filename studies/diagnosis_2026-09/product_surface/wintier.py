import sys, json, collections
cache = json.load(open(sys.argv[1], encoding="utf-8"))
DIRECT = ("Win the game", "damage", "lifeloss", "Lose the game", "Each opponent loses")
EFFECT = ("Infinite turns", "Infinite combat phases", "haste", "Infinitely large creature", "Infinitely powerful")
tot = direct = eff = 0
decks_with = decks_direct = 0
dup_rows = 0
for k, v in cache.items():
    inc = v.get("included", [])
    if inc: decks_with += 1
    d = 0
    seen = collections.Counter(tuple(sorted(c["cards"])) for c in inc)
    dup_rows += sum(n-1 for n in seen.values() if n > 1)
    for c in inc:
        tot += 1
        fs = c["produces"]
        if any(any(x in f for x in DIRECT) for f in fs):
            direct += 1; d += 1
        elif any(any(x in f for x in EFFECT) for f in fs):
            eff += 1
    if d: decks_direct += 1
print(f"variants={tot} direct_win={direct} ({direct/tot:.1%}) effective_win={eff} ({eff/tot:.1%}) engine/lock/value={tot-direct-eff} ({(tot-direct-eff)/tot:.1%})")
print(f"decks cached={len(cache)} with>=1 combo={decks_with} with>=1 direct-win combo={decks_direct}")
print("duplicate card-set rows (same cards listed twice):", dup_rows)
