import json, sys
from pathlib import Path
from math import comb
BASE=Path(r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability")
DECKS={'n7WpsqsZtdQ':['magda','rog_ishai','selvala_archetype','tymna_thrasios'],
       '2iA_Jt0d6sM':['derevi','godo_archetype','nadu','rograkh_silas']}
def fisher(a,b,c,d):
    # two-sided fisher exact for [[a,b],[c,d]]
    n=a+b+c+d; r1=a+b; c1=a+c
    def p(x): return comb(r1,x)*comb(n-r1,c1-x)/comb(n,c1)
    p0=p(a); tot=0
    for x in range(max(0,c1-(n-r1)),min(r1,c1)+1):
        px=p(x)
        if px<=p0*(1+1e-9): tot+=px
    return tot
def tally(arms):
    T={}
    for arm in arms:
        for line in open(BASE/arm/'results.jsonl'):
            r=json.loads(line)
            pod=r['pod']; rot=r['rotation']; decks=DECKS[pod]
            for s,deck in enumerate(decks):
                k=(deck,'plan' if s==rot else 'stock')
                t=T.setdefault(k,[0,0,0])
                t[0]+=r['wins_by_seat'].get(str(s+1),0); t[1]+=r['games']; t[2]+=r['decided']
    return T
for arms in [sys.argv[1:]]:
    T=tally(arms)
    print('arms',arms)
    for pod,decks in DECKS.items():
        for d in decks:
            p=T[(d,'plan')]; s=T[(d,'stock')]
            f=fisher(p[0],p[1]-p[0],s[0],s[1]-s[0])
            print(f"{d:20s} plan {p[0]:3d}/{p[1]:3d} ({p[0]/p[1]:.0%}) dec{p[2]}  stock {s[0]:3d}/{s[1]:3d} ({s[0]/s[1]:.0%}) dec{s[2]}  fisher p={f:.4f}")
    def grp(names):
        pw=sum(T[(d,'plan')][0] for d in names); pn=sum(T[(d,'plan')][1] for d in names)
        sw=sum(T[(d,'stock')][0] for d in names); sn=sum(T[(d,'stock')][1] for d in names)
        return pw,pn,sw,sn
    for label,names in [('oracle',['rograkh_silas','tymna_thrasios']),('engine5',['magda','nadu','selvala_archetype','rog_ishai','derevi']),('engine6+godo',['magda','nadu','selvala_archetype','rog_ishai','derevi','godo_archetype']),('all',[d for v in DECKS.values() for d in v])]:
        pw,pn,sw,sn=grp(names)
        print(f"{label:14s} plan {pw}/{pn} ({pw/pn:.1%}) stock {sw}/{sn} ({sw/sn:.1%}) fisher p={fisher(pw,pn-pw,sw,sn-sw):.4f}")
