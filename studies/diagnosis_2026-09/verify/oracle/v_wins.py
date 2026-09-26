import collections, glob, json, re, statistics, itertools
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
SETS = {
    "av_015_default": "agent_viability/runs_015_default/cell_*.jsonl",
    "av_winmax": "agent_viability/runs_winmax/cell_*.jsonl",
    "av_016_engine": "agent_viability/runs_016_engine/cell_*.jsonl",
    "br_agent_shipping": "behavior_rubric/runs_agent_shipping/*.jsonl",
    "tt_stage2": "tutor_targeting/runs_stage2/*.jsonl",
    "hc_stock": "human_ceiling/runs/*.jsonl",
    "br_agent_093": "behavior_rubric/runs_agent_093/*.jsonl",
    "br_agent_080": "behavior_rubric/runs_agent/*.jsonl",
    "tt_runs": "tutor_targeting/runs/*.jsonl",
    "tt_stage1": "tutor_targeting/runs_stage1/*.jsonl",
    "tt_stock": "tutor_targeting/runs_stock/*.jsonl",
}
W = collections.defaultdict(list)
for arm, pat in SETS.items():
    for f in sorted(glob.glob(S + pat)):
        meta=None; games=collections.defaultdict(list)
        for l in open(f, encoding="utf-8"):
            try: r=json.loads(l)
            except: continue
            if r.get("rec")=="meta": meta=r
            elif r.get("rec")=="entry": games[r["game"]].append(r)
        if not meta: continue
        agents=dict(zip(meta["players"],meta["agents"])); n=len(meta["players"])
        for g,es in games.items():
            es.sort(key=lambda r:r["seq"]); last=0; oc_turn=None
            for e in es:
                if e["type"]=="TURN":
                    m=re.match(r"Turn (\d+)",e["message"]); last=int(m.group(1)) if m else last
                if e["type"]=="GAME_OUTCOME":
                    m=re.match(r"Turn (\d+)$",e["message"])
                    if m: oc_turn=int(m.group(1))
                    m=re.match(r"(Ai\(\d\)-\S+) has won (.*)",e["message"])
                    if m:
                        W[arm].append((agents.get(m.group(1)),"oracle" if "Thassa" in m.group(2) else "other", last/n, oc_turn))
for arm,ws in W.items():
    o=[w for w in ws if w[1]=="oracle"]
    print(arm, "wins",len(ws),"oracle",len(o), "oracle stock",sum(1 for w in o if w[0]!="plan"))
def summ(arms):
    ws=[w for a in arms for w in W[a]]
    o=[w[2] for w in ws if w[1]=="oracle"]; x=[w[2] for w in ws if w[1]=="other"]
    o2=[w[3] for w in ws if w[1]=="oracle" and w[3]]; 
    return len(o), (statistics.median(o) if o else None), (min(o) if o else None),(max(o) if o else None), len(x), statistics.median(x) if x else None, (statistics.median(o2) if o2 else None)
arms=list(W)
# find subsets with 20 oracle / 393 other
for k in range(1,len(arms)+1):
    for sub in itertools.combinations(arms,k):
        s=summ(sub)
        if s[0]==20 and s[4]==393: print("MATCH",sub,s)
print("av only", summ(["av_015_default","av_winmax","av_016_engine"]))
print("av+brship+tt2", summ(["av_015_default","av_winmax","av_016_engine","br_agent_shipping","tt_stage2"]))
print("8 sets", summ(arms[:8]))
print("all", summ(arms))
