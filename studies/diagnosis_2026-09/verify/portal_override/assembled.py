import json, glob, collections
from math import comb
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ['runs_015_default','runs_winmax','runs_016_engine','runs_nocombo','runs_pilot']
plans=json.load(open(ROOT+'runs_015_default/plans_n7WpsqsZtdQ.json',encoding='utf-8'))['decks']['magda']
LINES=[set(l['cards']) for l in plans['lines']]
def fisher(a,b,c,d):
    n=a+b+c+d; r1=a+b; c1=a+c
    def p(x): return comb(r1,x)*comb(n-r1,c1-x)/comb(n,c1)
    p0=p(a); lo=max(0,c1-(n-r1)); hi=min(r1,c1)
    return sum(p(x) for x in range(lo,hi+1) if p(x)<=p0*(1+1e-9))
out=[]
for arm in ARMS:
    for f in sorted(glob.glob(ROOT+arm+'/cell_n7*.jsonl')):
        recs=[json.loads(l) for l in open(f,encoding='utf-8')]
        meta=recs[0]; mi=[i for i,p in enumerate(meta['players']) if p.endswith('-magda')][0]
        mp=meta['players'][mi]; agent=meta['agents'][mi]
        G=collections.defaultdict(lambda: dict(bf=collections.Counter(), assembled=set(), lib2bf=[], res=None, searches=0, combo_cast=0, portal_ov=0, cmd_bf=False))
        for r in recs:
            g=r.get('game')
            if g is None: continue
            x=G[g]
            if r['rec']=='entry' and r.get('type')=='STACK_RESOLVE' and r.get('card')=='Magda, Brazen Outlaw' and 'searches their library for an Artifact' in r.get('message',''):
                x['searches']+=1
            if r['rec']=='agent' and r.get('player')==mp:
                if r['event']=='combo_cast': x['combo_cast']+=1
                if r['event']=='tutor_steer' and 'over=Portal to Phyrexia' in r['detail']: x['portal_ov']+=1
            if r['rec']=='zone':
                c=r['card']
                if r.get('to')=='Battlefield' and r.get('toPlayer')==mp:
                    x['bf'][c]+=1
                    if r.get('from')=='Library' and 'Land' not in (r.get('types') or ''): x['lib2bf'].append(c)
                if r.get('from')=='Battlefield' and r.get('fromPlayer')==mp and x['bf'][c]>0:
                    x['bf'][c]-=1
                onbf={k for k,v in x['bf'].items() if v>0}
                for i,L in enumerate(LINES):
                    if L<=onbf: x['assembled'].add(i)
            if r['rec']=='result': x['res']=r
        for g,x in G.items():
            if x['res'] is None: continue
            out.append(dict(arm=arm,agent=agent,win=x['res']['winner']==mp,assembled=bool(x['assembled']),searches=x['searches'],lib2bf=x['lib2bf'],combo_cast=x['combo_cast'],portal_ov=x['portal_ov'],portal='Portal to Phyrexia' in x['bf'] ))
for arms,label in [(ARMS[:3],'lines3'),(ARMS[3:4],'nocombo')]:
    print('=====',label)
    for agent in ['plan','stock']:
        S=[r for r in out if r['arm'] in arms and r['agent']==agent]
        A=[r for r in S if r['assembled']]
        print(f" {agent}: games {len(S)}, line fully on bf in {len(A)} games, won {sum(r['win'] for r in A)} of those; combo_cast total {sum(r['combo_cast'] for r in S)}")
        c=collections.Counter(cc for r in S for cc in r['lib2bf'])
        print('   lib->bf nonland (all):', c.most_common(10))
    P=[r for r in out if r['arm'] in arms and r['agent']=='plan']
    ov=[r for r in P if r['portal_ov']>0]; nov=[r for r in P if r['portal_ov']==0 and r['searches']>0]
    print(f" plan games with >=1 Portal override: {len(ov)} won {sum(r['win'] for r in ov)}; plan games w/ Magda search but no Portal override: {len(nov)} won {sum(r['win'] for r in nov)}")
    S=[r for r in out if r['arm'] in arms and r['agent']=='stock' and r['searches']>0]
    sp=[r for r in S if r['portal']]
    print(f" stock games with Magda search: {len(S)}, Portal on bf in {len(sp)}, won {sum(r['win'] for r in sp)}; searched but no portal: {len(S)-len(sp)} won {sum(r['win'] for r in S if not r['portal'])}")
