import json, collections, os
HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "v2_rows.json")))
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies/"
EX = {"Demonic Consultation", "Tainted Pact"}
def ocat(o):
    if "Thassa's Oracle" in o and o.startswith("won"): return "WON_ORACLE"
    if "empty library" in o: return "DECKED"
    return "other"
cache = {}
res = collections.Counter()
for r in rows:
    if r["agent"] != "plan": continue
    ccO = [a for a in r["agentlog"] if a[1] == "combo_cast" and a[2].startswith("Thassa's Oracle")]
    o = ocat(r["outcome"])
    responded = any("TRIGGER ON STACK" in e[2] for e in r["events"])
    key = r["dir"] + "/" + r["file"]
    if key not in cache:
        z = collections.defaultdict(list)
        for line in open(ROOT + key, encoding="utf-8"):
            if '"rec":"zone"' in line and ('Oracle' in line or 'Consultation' in line or 'Tainted Pact' in line):
                q = json.loads(line); z[q["game"]].append(q)
        cache = {key: z}
    z = cache[key][r["game"]]
    hand = set(); state = []
    first = None
    for q in z:
        if q["card"] in EX:
            if q["to"] == "Hand" and q["toPlayer"] == r["player"]: hand.add(q["cardId"])
            elif q["from"] == "Hand" and q["fromPlayer"] == r["player"]: hand.discard(q["cardId"])
        if q["card"] == "Thassa's Oracle" and q["from"] == "Hand" and q["to"] == "Stack" and q["fromPlayer"] == r["player"] and first is None:
            first = (q["turn"], len(hand) > 0)
    tag = ("shimOracle" if ccO else "stockOracle", "responded" if responded else "trigger_resolved_unanswered",
           "exilerInHand" if (first and first[1]) else "noExilerInHand", o)
    res[tag] += 1
for k in sorted(res): print(k, res[k])
