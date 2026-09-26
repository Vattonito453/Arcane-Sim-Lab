import json,glob,pickle,collections,re,zipfile,sys,os
info=pickle.load(open("cardinfo.pkl","rb"))
# non-mana activated ability per card from script
Z=zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
ab={}
for n in Z.namelist():
    if not n.endswith(".txt"): continue
    t=Z.read(n).decode("utf-8","replace")
    nm=re.search(r"^Name:(.+)$",t,re.M)
    if not nm: continue
    lines=[l for l in t.splitlines() if l.startswith("A:AB$")]
    ab[nm.group(1).strip()]=any(not re.match(r"A:AB\$ ?Mana\b",l) for l in lines)
R="C:/Users/Vatto/Magic Rules Engine/studies/"
tot=collections.Counter(); per=collections.Counter()
for fold in sys.argv[1:]:
    for f in sorted(glob.glob(R+fold+"/*.jsonl")):
        names=collections.defaultdict(set); onbf={}; act=set()
        for l in open(f,encoding="utf-8",errors="replace"):
            if '"rec":"zone"' in l:
                r=json.loads(l); k=(r["game"],r.get("cardId")); names[k].add(r.get("card"))
                if r.get("to")=="Battlefield" and not r.get("token"): onbf.setdefault(k,r.get("card"))
            elif '"STACK_ADD"' in l and " activated " in l:
                r=json.loads(l); act.add((r["game"],r.get("cardId")))
        for k,nm in onbf.items():
            c=info.get(nm)
            if not c or not ab.get(nm): continue
            orig = names[k]=={nm}
            key=(c["fl"], "orig" if orig else "copy/other")
            tot[key+("bf",)]+=1; tot[key+("act",)]+= k in act
            if c["fl"]=="All": per[(nm,"orig" if orig else "copy", k in act)]+=1
for fl in ("All","Random","none"):
    for o in ("orig","copy/other"):
        b=tot[(fl,o,"bf")]; a=tot[(fl,o,"act")]
        if b: print("%-6s %-10s onBF=%5d activated=%5d rate=%.3f"%(fl,o,b,a,a/b))
print(sorted(per.items(),key=lambda kv:-kv[1])[:30])
