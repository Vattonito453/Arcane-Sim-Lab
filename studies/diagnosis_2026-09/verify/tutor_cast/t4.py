import json, collections, sys
sys.path.insert(0,'.')
from cmdgate import sight, S, DIRS
out=collections.Counter()
for d in DIRS:
    for deck, cell in (("godo_archetype", "cell_2iA_Jt0d6sM_rot1.jsonl"), ("magda", "cell_n7WpsqsZtdQ_rot0.jsonl")):
        pod = "2iA_Jt0d6sM" if "2iA" in cell else "n7WpsqsZtdQ"
        plan = json.load(open(S + d + "/plans_" + pod + ".json", encoding="utf-8"))["decks"][deck]
        commander = "Godo, Bandit Warlord" if deck.startswith("godo") else "Magda, Brazen Outlaw"
        zones = collections.defaultdict(list); me=None
        for l in open(S + d + "/" + cell, encoding="utf-8"):
            if '"rec":"meta"' in l:
                r=json.loads(l); me=[p for p,a in zip(r["players"],r["agents"]) if a=="plan"][0]
            elif '"rec":"zone"' in l:
                r=json.loads(l); zones[r["game"]].append(r)
        for g, zs in zones.items():
            state={}; opened=None; opened_nc=None; which=None
            for i,z in enumerate(zs):
                if (z.get("turn") or 0) > 4: break
                if not z.get("token"): state[z["cardId"]]=(z["to"],z.get("toPlayer"),z["card"])
                board={n for (zn,p,n) in state.values() if zn=="Battlefield" and p==me}
                hand={n for (zn,p,n) in state.values() if zn=="Hand" and p==me}
                cmd={n for (zn,p,n) in state.values() if zn=="Command" and p==me}
                if not any(x["card"]==commander and x.get("fromPlayer")==me for x in zs[:i+1]): cmd.add(commander)
                s1=sight(plan,board,hand,cmd,True); s2=sight(plan,board,hand,cmd,False)
                if s1 and opened is None: opened=z.get("turn"); which=s1
                if s2 and opened_nc is None: opened_nc=z.get("turn")
            out[(deck,'replica gate open by turn4')]+= opened is not None
            out[(deck,'open by turn4 w/o commander-as-tutor')]+= opened_nc is not None
            if which: out[(deck,'first line '+' + '.join(which[0]))]+=1
for k,v in sorted(out.items()): print(v,k)
