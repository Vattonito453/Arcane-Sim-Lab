import json, glob, collections, sys, math
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ['runs_015_default','runs_winmax','runs_016_engine','runs_nocombo','runs_pilot']
def fisher(a,b,c,d):
    # two-sided Fisher exact for [[a,b],[c,d]]
    from math import comb
    n=a+b+c+d; r1=a+b; c1=a+c
    def p(x): return comb(r1,x)*comb(n-r1,c1-x)/comb(n,c1)
    p0=p(a); lo=max(0,c1-(n-r1)); hi=min(r1,c1)
    return sum(p(x) for x in range(lo,hi+1) if p(x)<=p0*(1+1e-9))
rows=[]
for arm in ARMS:
    for f in sorted(glob.glob(ROOT+arm+'/cell_*.jsonl')):
        meta=None; games={}
        for l in open(f,encoding='utf-8'):
            r=json.loads(l)
            if r['rec']=='meta': meta=r; continue
            g=r.get('game')
            if g is None: continue
            G=games.setdefault(g,{'portal_bf':set(),'portal_cast':set(),'res':None})
            if r['rec']=='zone' and r.get('card')=='Portal to Phyrexia' and r.get('to')=='Battlefield':
                G['portal_bf'].add(r.get('toPlayer'))
            if r['rec']=='result': G['res']=r
        for i,p in enumerate(meta['players']):
            deck=p.split('-',1)[1]
            for g,G in games.items():
                if G['res'] is None: continue
                rows.append(dict(arm=arm,file=f,deck=deck,agent=meta['agents'][i],game=g,
                    win=G['res']['winner']==p, decided=G['res']['winner'] is not None and not G['res'].get('draw'),
                    portal=p in G['portal_bf'], turns=G['res']['turns']))
json.dump(rows,open('rows.json','w'))
def tab(sel, label):
    n=len(sel); w=sum(r['win'] for r in sel)
    return f"{label}: {w}/{n} ({100*w/max(n,1):.0f}%)"
print("== Magda plan vs stock, per arm")
tot={'plan':[0,0],'stock':[0,0]}
for arm in ARMS:
    ps=[r for r in rows if r['arm']==arm and r['deck']=='magda' and r['agent']=='plan']
    ss=[r for r in rows if r['arm']==arm and r['deck']=='magda' and r['agent']=='stock']
    print(arm, tab(ps,'plan'), tab(ss,'stock'), 'portal_bf plan', sum(r['portal'] for r in ps), 'stock', sum(r['portal'] for r in ss))
for arms,label in [(ARMS[:3],'3 with-lines arms'),(ARMS[:4],'4 arms incl nocombo'),(ARMS,'all 5')]:
    ps=[r for r in rows if r['arm'] in arms and r['deck']=='magda' and r['agent']=='plan']
    ss=[r for r in rows if r['arm'] in arms and r['deck']=='magda' and r['agent']=='stock']
    a=sum(r['win'] for r in ps); b=len(ps)-a; c=sum(r['win'] for r in ss); d=len(ss)-c
    print(label, tab(ps,'plan'), tab(ss,'stock'), 'fisher p=%.4f'%fisher(a,b,c,d), 'plan portal_bf', sum(r['portal'] for r in ps),'/',len(ps))
print("== every deck: plan vs stock win share (3 with-lines arms)")
for deck in sorted(set(r['deck'] for r in rows)):
    for arms,label in [(ARMS[:3],'lines3'),(['runs_nocombo'],'nocombo')]:
        ps=[r for r in rows if r['arm'] in arms and r['deck']==deck and r['agent']=='plan']
        ss=[r for r in rows if r['arm'] in arms and r['deck']==deck and r['agent']=='stock']
        a=sum(r['win'] for r in ps); b=len(ps)-a; c=sum(r['win'] for r in ss); d=len(ss)-c
        print(f"  {deck:20s} {label:8s}", tab(ps,'plan'), tab(ss,'stock'), 'p=%.3f'%fisher(a,b,c,d))
print("== stock-seat Magda, P(win | Portal on bf)")
for arms,label in [(ARMS[:4],'4 arms'),(ARMS,'5 arms')]:
    ss=[r for r in rows if r['arm'] in arms and r['deck']=='magda' and r['agent']=='stock']
    y=[r for r in ss if r['portal']]; n=[r for r in ss if not r['portal']]
    print(label, tab(y,'portal'), tab(n,'no portal'))
    print('   median turns portal', sorted(r['turns'] for r in y)[len(y)//2] if y else None, 'no portal', sorted(r['turns'] for r in n)[len(n)//2])
