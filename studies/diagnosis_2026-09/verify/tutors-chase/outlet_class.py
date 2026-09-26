import json, glob, re, collections
from pathlib import Path
LU = json.load(open("lines_union.json"))
BC = json.load(open("bycard.json"))
D = "C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks"
deckcards = {}
for f in glob.glob(D + "/*/dck/*.dck"):
    names = set()
    for ln in open(f, encoding="utf-8"):
        m = re.match(r"^\s*\d+\s+(.+?)\s*(\|.*)?$", ln)
        if m: names.add(m.group(1).strip())
    deckcards.setdefault(Path(f).stem, set()).update(names)
MANA_OUT = {"Thrasios, Triton Hero", "Kinnan, Bonder Prodigy", "Finale of Devastation", "Staff of Domination",
            "Walking Ballista", "Blue Sun's Zenith", "Stroke of Genius", "Torment of Hailfire", "Hydroid Krasis",
            "Magda, Brazen Outlaw"}
DRAW_OUT = {"Thassa's Oracle", "Laboratory Maniac", "Jace, Wielder of Mysteries", "Finale of Devastation"}
STORM_OUT = {"Brain Freeze", "Grapeshot", "Aetherflux Reservoir", "Tendrils of Agony", "Empty the Warrens"}
MILL_OUT = {"Laboratory Maniac", "Jace, Wielder of Mysteries", "Underworld Breach"}
def bucket(deck, card):
    dc = deckcards.get(deck, set())
    best = "resource-no-outlet"
    for cards, prod in LU.get(deck, []):
        if card not in cards: continue
        P = " | ".join(prod)
        if "Put all" in P: return "put-all-onto-battlefield"
        if re.search(r"(Infinite|Near-infinite) (colored |colorless |green |)mana|mana .*can produce|mana of colors", P) and dc & MANA_OUT:
            return "infinite-mana+outlet-in-deck"
        if re.search(r"(Infinite|Near-infinite) card draw", P) and dc & DRAW_OUT: return "infinite-draw+outlet"
        if "storm count" in P and dc & STORM_OUT: return "storm+payoff"
        if "self-mill" in P and dc & MILL_OUT: return "self-mill+outlet"
    return best
out = collections.Counter(); per = collections.defaultdict(collections.Counter)
for k, v in BC.items():
    mode, cls, deck, card = k.split("|", 3)
    if cls != "resource": continue
    b = bucket(deck, card); out[(mode, b)] += v; per[b][(deck, card)] += v
for mode in ("combo", "plan", "tutor_cast"):
    tot = sum(v for (m, b), v in out.items() if m == mode)
    print(mode, "resource total", tot, {b: v for (m, b), v in sorted(out.items()) if m == mode})
tot = sum(out.values()); nooutlet = sum(v for (m, b), v in out.items() if b == "resource-no-outlet")
print("ALL resource", tot, "no outlet", nooutlet, round(100*nooutlet/tot))
print("top no-outlet:", per["resource-no-outlet"].most_common(15))
