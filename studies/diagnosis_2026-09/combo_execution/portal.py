import json, glob, os, collections
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_n7*.jsonl", "agent_viability/runs_winmax/cell_n7*.jsonl",
        "agent_viability/runs_016_engine/cell_n7*.jsonl"]
c = collections.Counter()
for pat in PATS:
    for f in glob.glob(S + pat):
        recs = [json.loads(l) for l in open(f, encoding="utf-8")]
        meta = recs[0]; agents = dict(zip(meta["players"], meta["agents"]))
        res = {r["game"]: r["winner"] for r in recs if r.get("rec") == "result"}
        portal = set(); games = set(res)
        for r in recs:
            if r.get("rec") == "zone" and r["card"] == "Portal to Phyrexia" and r["to"] == "Battlefield":
                portal.add((r["game"], r["toPlayer"]))
        mag = [p for p in agents if p.endswith("magda")][0]
        for g in games:
            k = (agents[mag], "Portal hit battlefield" if (g, mag) in portal else "no Portal")
            c[k + ("won",)] += res[g] == mag
            c[k + ("games",)] += 1
for ag in ("plan", "stock"):
    for pk in ("Portal hit battlefield", "no Portal"):
        n = c[(ag, pk, "games")]; w = c[(ag, pk, "won")]
        print(f"magda {ag:5s} {pk:22s} games={n:3d} won={w:3d} ({100*w/max(1,n):.0f}%)")
