import json, glob, os, pickle, re, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__))
info = pickle.load(open(os.path.join(HERE, "cardinfo.pkl"), "rb"))
def ci(n):
    n=n.strip(); return info.get(n) or info.get(n.split(" // ")[0])
def fl(n):
    c=ci(n); return c["fl"] if c else "unk"
R = "C:/Users/Vatto/Magic Rules Engine/studies/"
L=0; FL=0; pieces=set(); fp=set(); tut=set(); ft=set(); flnames=collections.Counter(); ftn=collections.Counter()
for f in sorted(glob.glob(R+"behavior_rubric/plans_*.json")):
    D=json.load(open(f,encoding="utf-8"))["decks"]
    for deck,p in D.items():
        for line in p.get("lines",[]):
            cs=line["cards"] if isinstance(line,dict) else line
            L+=1
            fx=[c for c in cs if fl(c)=="All"]
            if fx: FL+=1; flnames.update(fx)
            for c in cs:
                pieces.add((deck,c))
                if fl(c)=="All": fp.add((deck,c))
        for t in p.get("tutors",[]):
            tut.add((deck,t))
            if fl(t)=="All": ft.add((deck,t)); ftn[t]+=1
print("behavior_rubric plans: lines=%d linesWithAllFlagged=%d (%.3f) distinct(deck,piece)=%d flagged=%d tutors(deck,t)=%d flaggedTutors=%d"%(L,FL,FL/L,len(pieces),len(fp),len(tut),len(ft)))
print("flagged pieces most common in lines:",flnames.most_common(20))
print("flagged tutors:",ftn.most_common(20))
# precon nonland flagged per deck
decks=set()
for f in glob.glob(R+"precon_predict/runs_stock/*.jsonl"):
    with open(f,encoding="utf-8") as fh:
        for d in json.loads(fh.readline()).get("decks",[]): decks.add(d)
Z=__import__("zipfile").ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
# land detection from card script Types line
landset={}
for n in Z.namelist():
    if not n.endswith(".txt"): continue
    t=Z.read(n).decode("utf-8","replace")
    nm=re.search(r"^Name:(.+)$",t,re.M); ty=re.search(r"^Types:(.+)$",t,re.M)
    if nm and ty: landset[nm.group(1).strip()]="Land" in ty.group(1).split()
per=[]; perl=[]
for d in sorted(decks):
    sec=None; a=0; al=0
    for line in open(d.replace("\\","/"),encoding="utf-8",errors="replace"):
        line=line.strip()
        if line.startswith("["): sec=line.lower(); continue
        if sec not in ("[main]","[commander]"): continue
        m=re.match(r"(\d+)\s+([^|]+)",line)
        if not m: continue
        nm=m.group(2).strip()
        if fl(nm)=="All":
            if landset.get(nm): al+=1
            else: a+=1
    per.append(a); perl.append(al)
print("precon flagged NONLAND per deck mean %.2f median %s max %d; flagged LANDS per deck mean %.2f"%(statistics.mean(per),statistics.median(per),max(per),statistics.mean(perl)))
