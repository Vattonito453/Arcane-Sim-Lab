import json, glob, collections, re, sys
S = "C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
arms = sys.argv[1:]
wins = collections.Counter()   # (arm-group, agent, deck, method)
losses_self = collections.Counter()
for arm in arms:
    for f in sorted(glob.glob(S + arm + "/cell_*.jsonl")):
        agents=None; outs=collections.defaultdict(list)
        res={}
        for l in open(f, encoding="utf-8"):
            if '"rec":"meta"' in l:
                r=json.loads(l); agents=dict(zip(r["players"], r["agents"]))
            elif '"GAME_OUTCOME"' in l:
                r=json.loads(l); outs[r["game"]].append(r["message"])
            elif '"rec":"result"' in l:
                r=json.loads(l); res[r["game"]]=r
        for g,r in res.items():
            w=r["winner"]
            msgs=outs.get(g,[])
            method="combat/life"
            for m in msgs:
                if "won due to effect of" in m or "won by spell" in m:
                    method="alt-win:"+m.split("'")[1]; break
            if w is None:
                method="draw"
            else:
                if method=="combat/life":
                    others=[m for m in msgs if "has lost" in m]
                    if others and not all("life total" in m for m in others):
                        method="mixed-loss"
                d=w.split("-",1)[1]
                wins[(agents[w], d, method)]+=1
            for m in msgs:
                if "empty library" in m or "due to effect of spell" in m:
                    p=m.split(" ")[0]
                    losses_self[(agents.get(p), p.split("-",1)[1], re.sub(r"Ai\(\d\)-\S+ ","",m))]+=1
for k in sorted(wins): print(wins[k], k)
print("--- self-inflicted-looking losses")
for k in sorted(losses_self, key=str): print(losses_self[k], k)
