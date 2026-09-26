import json, glob, os, collections
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_*.jsonl", "agent_viability/runs_winmax/cell_*.jsonl",
        "agent_viability/runs_016_engine/cell_*.jsonl", "behavior_rubric/runs_agent_shipping/*.jsonl",
        "tutor_targeting/runs_stage2/*.jsonl", "human_ceiling/runs/*.jsonl"]
c = collections.Counter(); casts = collections.Counter(); perturn = collections.Counter()
for pat in PATS:
    for f in glob.glob(S + pat):
        recs = [json.loads(l) for l in open(f, encoding="utf-8")]
        agents = dict(zip(recs[0]["players"], recs[0]["agents"]))
        onbf = {}
        for r in recs:
            if r.get("rec") != "zone":
                continue
            k = (r["game"], r.get("toPlayer") or r.get("fromPlayer"))
            if r["card"] == "Underworld Breach":
                if r["to"] == "Battlefield":
                    onbf[(r["game"], r["toPlayer"])] = r["turn"]; c[("breach entered", agents.get(r["toPlayer"]))] += 1
                elif r["from"] == "Battlefield":
                    onbf.pop((r["game"], r["fromPlayer"]), None)
            if r["from"] == "Graveyard" and r["to"] == "Stack":
                p = r["fromPlayer"]
                if (r["game"], p) in onbf:
                    casts[(agents.get(p), r["card"])] += 1
                    perturn[(f, r["game"], p, r["turn"])] += 1
print(dict(c))
print("graveyard casts while that player's Breach was on the battlefield:", sum(casts.values()), casts.most_common(10))
print("max escape casts in one turn:", max(perturn.values()) if perturn else 0)
