import sys, math
sys.argv=[sys.argv[0]]
from tallylib import tally
arms=["runs_015_default","runs_winmax","runs_016_engine","runs_nocombo"]
T={a:tally(a) for a in arms}
decks=sorted({k[1] for k in T[arms[0]]})
print(f"{'deck':20s}"+"".join(f"{a[5:]:>26s}" for a in arms))
for d in decks:
    row=f"{d:20s}"
    for a in arms:
        t=T[a]
        pw,pn,sw,sn=t[("plan",d,"w")],t[("plan",d,"n")],t[("stock",d,"w")],t[("stock",d,"n")]
        row+=f"   {pw:2d}/{pn} vs {sw:2d}/{sn} {100*(pw/pn-sw/sn):+6.1f}"
    print(row)
