import json, glob, collections, re, sys
R = "C:/Users/Vatto/Magic Rules Engine/studies/behavior_rubric/runs_agent_shipping/plans"
STRICT = {"Win the game"}
# features that end the game without an extra card (given the listed pieces)
LENIENT_EXTRA = {
 "Near-infinite damage", "Infinite creature tokens with haste", "Infinite combat phases",
 "Infinitely large creature until end of turn", "Infinitely powerful creatures you control until end of turn",
 "Infinite power for any creature", "Near-infinite mill", "Infinite mill",
}
def cls(prod, mode):
    s = set(prod)
    if s & STRICT: return "win"
    if mode == "lenient" and s & LENIENT_EXTRA: return "win"
    return "resource"
rows = []
for f in sorted(glob.glob(R + "/plans_*.json")):
    pod = f.split("plans_")[-1][:-5]
    d = json.load(open(f, encoding="utf-8"))
    for name, plan in d["decks"].items():
        for ln in plan.get("lines", []):
            rows.append((pod, name, ln["cards"], ln.get("produces", [])))
for mode in ("strict", "lenient"):
    c = collections.Counter(cls(r[3], mode) for r in rows)
    per = collections.defaultdict(lambda: [0,0])
    for r in rows:
        per[(r[0], r[1])][0] += 1
        per[(r[0], r[1])][1] += cls(r[3], mode) == "win"
    zero = [(k, v) for k, v in per.items() if v[1] == 0]
    print(mode, dict(c), "decks with lines", len(per), "zero-win decks", len(zero))
    for k, v in sorted(zero): print("   ", k, f"{v[1]}/{v[0]}")
if "-v" in sys.argv:
    for r in rows:
        print(r[0][:4], r[1][:30], "|", " + ".join(r[2]), "->", "; ".join(r[3]))
