import json, glob, os, pickle, collections, sys
HERE=os.path.dirname(os.path.abspath(__file__))
info=pickle.load(open(os.path.join(HERE,"cardinfo.pkl"),"rb"))
R="C:/Users/Vatto/Magic Rules Engine/studies/"
for fold in sys.argv[1:]:
    c=collections.Counter(); ex=collections.defaultdict(list)
    for f in sorted(glob.glob(R+fold+"/*.jsonl")):
        agent_of={}
        for l in open(f,encoding="utf-8",errors="replace"):
            if '"STACK_ADD"' not in l and '"rec":"meta"' not in l: continue
            r=json.loads(l)
            if r.get("rec")=="meta":
                for p,a in zip(r.get("players",[]),r.get("agents",[])): agent_of[p]="stock" if a=="stock" else "plan"
                continue
            m=r.get("message","")
            if " activated " not in m: continue
            nm=r.get("card"); ci=info.get(nm)
            if not ci or ci["fl"]!="All": continue
            pl=m.split(" activated ")[0]
            a=agent_of.get(pl,"?")
            c[(a,nm)]+=1
            if len(ex[(a,nm)])<2: ex[(a,nm)].append((os.path.basename(f),r.get("game"),r.get("seq"),m[:160]))
    print("==",fold)
    for k,v in sorted(c.items(),key=lambda kv:-kv[1]): print("  ",k,v,ex[k])
