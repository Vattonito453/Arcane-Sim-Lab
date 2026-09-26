import json, re, collections
rows = json.load(open("all_lines.json"))
# per-deck dedup
seen = set(); dl = []
for r in rows:
    k = (r["pod"], r["deck"], tuple(sorted(r["cards"])))
    if k in seen: continue
    seen.add(k); dl.append(r)
WIN = re.compile(r"win the game|damage|lose the game|life ?loss|infinite combat|(?<!self-)mill\b|each opponent", re.I)
def steps(r): return [s.strip() for s in r["description"].split("\n") if s.strip()]
def is_act(s): return s.lower().startswith("activate") or " activate " in s.lower()[:40] or s.lower().startswith("holding priority, activate")
def is_mana_act(s):
    s2 = s.lower()
    return is_act(s) and ("adding" in s2) and not any(w in s2 for w in ("untapping", "blinking", "returning", "sacrificing three", "creating", "exile", "sacrificing mana crypt", "targeting", "mill"))
def classify(r):
    st = steps(r)
    acts = [s for s in st if is_act(s)]
    nonmana = [s for s in acts if not is_mana_act(s)]
    win = any(WIN.search(p) for p in r["produces"])
    return dict(act=bool(acts), nonmana=bool(nonmana), win=win, prereq=bool(r["prerequisites"].strip()))
C = [dict(r=r, **classify(r)) for r in dl]
n = len(C)
print("deck-line pairs:", n)
print("  >=1 'Activate' step:", sum(c["act"] for c in C))
print("  >=1 NON-mana activation step:", sum(c["nonmana"] for c in C))
print("  produces a win/damage/opponent-mill/combat outcome:", sum(c["win"] for c in C), "-> no outcome:", n - sum(c["win"] for c in C))
print("  non-empty prerequisite:", sum(c["prereq"] for c in C))
exe = [c for c in C if not c["nonmana"] and c["win"]]
print("  no non-mana activation AND win outcome:", len(exe))
cnt = collections.Counter(" + ".join(sorted(c["r"]["cards"])) for c in exe)
for k, v in cnt.most_common(): print("     ", v, k)
exe2 = [c for c in exe if "Tainted Pact" not in c["r"]["cards"]]
print("  ...minus Tainted Pact:", len(exe2))
decks = {(c["r"]["pod"], c["r"]["deck"]) for c in exe2}
print("  decks with >=1 such line:", len(decks), "/ 32")
# global unique basis
gu = {}
for c in C: gu.setdefault(tuple(sorted(c["r"]["cards"])), c)
G = list(gu.values())
print("GLOBAL unique lines:", len(G), " nonmana act:", sum(c["nonmana"] for c in G), " any act:", sum(c["act"] for c in G), " win:", sum(c["win"] for c in G), " prereq:", sum(c["prereq"] for c in G), " exe:", sum(1 for c in G if not c["nonmana"] and c["win"]))
json.dump([dict(cards=c["r"]["cards"], deck=c["r"]["deck"], pod=c["r"]["pod"], act=c["act"], nonmana=c["nonmana"], win=c["win"], prereq=c["prereq"]) for c in C], open("mine.json", "w"), indent=1)
