import json, glob, statistics
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
arr = []; gap = []
for pat in ["agent_viability/runs_015_default/cell_n7*.jsonl", "agent_viability/runs_winmax/cell_n7*.jsonl", "agent_viability/runs_016_engine/cell_n7*.jsonl", "human_ceiling/runs/*n7*.jsonl"]:
    for f in glob.glob(S + pat):
        recs = [json.loads(l) for l in open(f, encoding="utf-8")]
        agents = dict(zip(recs[0]["players"], recs[0]["agents"]))
        res = {r["game"]: r for r in recs if r.get("rec") == "result"}
        seen = set()
        for r in recs:
            if r.get("rec") == "zone" and r["card"] == "Portal to Phyrexia" and r["to"] == "Battlefield" and r["toPlayer"].endswith("magda") and agents.get(r["toPlayer"]) == "stock":
                if r["game"] in seen: continue
                seen.add(r["game"]); arr.append(r["turn"] / 4)
                rr = res.get(r["game"])
                if rr and rr["winner"] == r["toPlayer"]:
                    gap.append((rr["turns"] - r["turn"]) / 4)
print("stock Magda Portal arrivals:", len(arr), "median round", statistics.median(arr), "p25", sorted(arr)[len(arr)//4])
print("Portal -> win (winners):", len(gap), "median rounds", statistics.median(gap))
