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
def z(w1,n1,w2,n2):
    p1=w1/n1; p2=w2/n2
    se=math.sqrt(p1*(1-p1)/n1+p2*(1-p2)/n2)
    return 100*p1,100*p2,100*(p1-p2),(p1-p2)/se if se else float('nan')
arms = sys.argv[1:]
tot = collections.Counter()
decks=set()
for arm in arms:
    T = tally(arm)
    for k,v in T.items(): tot[k]+=v; decks.add(k[1])
    g = collections.Counter()
    for (a,d,m),v in T.items():
        grp = "oracle" if d in ORACLE else "other"
        g[(grp,a,m)] += v
    for grp in ("oracle","other"):
        r = z(g[(grp,"plan","w")],g[(grp,"plan","n")],g[(grp,"stock","w")],g[(grp,"stock","n")])
        print(f"{arm:18s} {grp:6s} plan {g[(grp,'plan','w')]}/{g[(grp,'plan','n')]}={r[0]:.1f}% stock {g[(grp,'stock','w')]}/{g[(grp,'stock','n')]}={r[1]:.1f}% diff {r[2]:+.1f}pp ({r[3]:+.1f} SE)")
print("---- pooled", arms)
g = collections.Counter()
for (a,d,m),v in tot.items():
    grp = "oracle" if d in ORACLE else "other"
    g[(grp,a,m)] += v
    g[("all",a,m)] += v
for grp in ("oracle","other","all"):
    r = z(g[(grp,"plan","w")],g[(grp,"plan","n")],g[(grp,"stock","w")],g[(grp,"stock","n")])
    print(f"{grp:6s} plan {g[(grp,'plan','w')]}/{g[(grp,'plan','n')]}={r[0]:.1f}% stock {g[(grp,'stock','w')]}/{g[(grp,'stock','n')]}={r[1]:.1f}% diff {r[2]:+.1f}pp ({r[3]:+.1f} SE)")
print("---- per deck pooled")
for d in sorted(decks):
    r = z(tot[("plan",d,"w")],tot[("plan",d,"n")],tot[("stock",d,"w")],tot[("stock",d,"n")])
    print(f"{d:22s} plan {tot[('plan',d,'w')]}/{tot[('plan',d,'n')]}={r[0]:.1f}%  stock {tot[('stock',d,'w')]}/{tot[('stock',d,'n')]}={r[1]:.1f}%  {r[2]:+.1f}pp ({r[3]:+.1f} SE)  decided plan {tot[('plan',d,'dec')]} stock {tot[('stock',d,'dec')]}")
