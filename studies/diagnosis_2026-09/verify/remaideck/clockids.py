import json, glob, collections, sys
R="C:/Users/Vatto/Magic Rules Engine/studies/"
for fold in sys.argv[1:]:
    tally=collections.Counter()
    for f in sorted(glob.glob(R+fold+"/*.jsonl")):
        names=collections.defaultdict(set)  # (g,cid)->names seen in zone records
        acts=[]
        for l in open(f,encoding="utf-8",errors="replace"):
            if '"rec":"zone"' in l:
                r=json.loads(l); names[(r["game"],r.get("cardId"))].add(r.get("card"))
            elif '"STACK_ADD"' in l and "activated Clock of Omens" in l:
                r=json.loads(l); acts.append((r["game"],r.get("cardId"),r["message"].split(" activated")[0]))
        for g,cid,p in acts:
            ns=names.get((g,cid),set())
            tally[(p.split("-",1)[1], "orig" if ns=={"Clock of Omens"} else "other:"+"|".join(sorted(ns)))]+=1
    print("==",fold)
    for k,v in tally.most_common(): print("  ",k,v)
