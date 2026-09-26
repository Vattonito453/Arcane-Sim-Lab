import json, glob, collections, math, sys
S = "C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ORACLE = {"tymna_thrasios", "rograkh_silas"}
def tally(arm):
    t = collections.Counter()
    for f in sorted(glob.glob(S + arm + "/cell_*.jsonl")):
        agents = None
        seen = set()
        for l in open(f, encoding="utf-8"):
            if '"rec":"meta"' not in l and '"rec":"result"' not in l:
                continue
            r = json.loads(l)
            if r["rec"] == "meta":
                agents = dict(zip(r["players"], r["agents"]))
            elif r["rec"] == "result":
                if r["game"] in seen: print("dup", f, r["game"]); continue
                seen.add(r["game"])
                for p, a in agents.items():
                    d = p.split("-", 1)[1]
                    t[(a, d, "n")] += 1
                    t[(a, d, "w")] += (r["winner"] == p)
                    t[(a, d, "dec")] += (r["winner"] is not None)
    return t
