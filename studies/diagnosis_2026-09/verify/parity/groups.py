import sys, math
from tallylib import tally
G={"A_n7_nonoracle":("magda","rog_ishai","selvala_archetype"),
   "B_2iA_nonoracle":("derevi","godo_archetype","nadu"),
   "oracle":("tymna_thrasios","rograkh_silas")}
def agg(arms,decks):
    w=n=sw=sn=0
    for a in arms:
        t=tally(a)
        for d in decks:
            w+=t[("plan",d,"w")]; n+=t[("plan",d,"n")]; sw+=t[("stock",d,"w")]; sn+=t[("stock",d,"n")]
    p1,p2=w/n,sw/sn; se=math.sqrt(p1*(1-p1)/n+p2*(1-p2)/sn)
    return f"plan {w}/{n}={100*p1:.1f}% stock {sw}/{sn}={100*p2:.1f}% {100*(p1-p2):+.1f}pp ({(p1-p2)/se:+.1f} SE)", (w,n)
for g,decks in G.items():
    print(g)
    for label,arms in [("lines, 3 arms",["runs_015_default","runs_winmax","runs_016_engine"]),("winmax (0.5.0, lines)",["runs_winmax"]),("nocombo (0.5.0, no lines)",["runs_nocombo"])]:
        s,_=agg(arms,decks); print(f"   {label:28s} {s}")
    _,(w1,n1)=agg(["runs_winmax"],decks); _,(w2,n2)=agg(["runs_nocombo"],decks)
    p1,p2=w1/n1,w2/n2; se=math.sqrt(p1*(1-p1)/n1+p2*(1-p2)/n2)
    print(f"   ablation plan-seat winmax-nocombo {100*(p1-p2):+.1f}pp ({(p1-p2)/se:+.1f} SE)")
