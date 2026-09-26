import json, glob, collections, os
R = "C:/Users/Vatto/Magic Rules Engine/studies/behavior_rubric/runs_agent_shipping/plans"
feat = collections.Counter()
nlines = 0; ndecks = 0
for f in sorted(glob.glob(R + "/plans_*.json")):
    d = json.load(open(f, encoding="utf-8"))
    for name, plan in d["decks"].items():
        ndecks += 1
        for ln in plan.get("lines", []):
            nlines += 1
            for p in ln.get("produces", []):
                feat[p] += 1
print("decks", ndecks, "lines", nlines)
for k, v in feat.most_common():
    print(v, "|", k)
