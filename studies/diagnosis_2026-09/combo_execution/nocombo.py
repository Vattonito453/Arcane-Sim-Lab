import json, glob, collections, math
S = "C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
def tally(arm):
    t = collections.Counter()
    for f in glob.glob(S + arm + "/cell_*.jsonl"):
        meta = None
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            if r.get("rec") == "meta":
                meta = r; agents = dict(zip(r["players"], r["agents"]))
            elif r.get("rec") == "result":
                for p, a in agents.items():
                    d = p.split("-", 1)[1]
                    t[(a, d, "n")] += 1
                    t[(a, d, "w")] += (r["winner"] == p)
                    t[(a, d, "draw")] += (r["winner"] is None)
    return t
W, N = tally("runs_winmax"), tally("runs_nocombo")
decks = sorted({k[1] for k in W})
grp = {"oracle": ("tymna_thrasios", "rograkh_silas")}
agg = collections.Counter()
for d in decks:
    g = "oracle" if d in grp["oracle"] else "other"
    wn, ww = W[("plan", d, "n")], W[("plan", d, "w")]
    nn, nw = N[("plan", d, "n")], N[("plan", d, "w")]
    agg[(g, "wn")] += wn; agg[(g, "ww")] += ww; agg[(g, "nn")] += nn; agg[(g, "nw")] += nw
    print(f"{d:20s} plan WITH lines (winmax) {ww}/{wn}={100*ww/max(1,wn):.0f}%   plan WITHOUT lines (nocombo) {nw}/{nn}={100*nw/max(1,nn):.0f}%")
for g in ("oracle", "other"):
    p1 = agg[(g, "ww")] / agg[(g, "wn")]; p2 = agg[(g, "nw")] / agg[(g, "nn")]
    se = math.sqrt(p1*(1-p1)/agg[(g, "wn")] + p2*(1-p2)/agg[(g, "nn")])
    print(f"{g}: with lines {100*p1:.1f}% (n={agg[(g,'wn')]}) vs without {100*p2:.1f}% (n={agg[(g,'nn')]}): {100*(p1-p2):+.1f}pp ({(p1-p2)/se:+.1f} SE)")
