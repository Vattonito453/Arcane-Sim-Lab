import json, glob, collections
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ['runs_015_default','runs_winmax','runs_016_engine','runs_nocombo','runs_pilot']
from wins import fisher
out=[]
for arm in ARMS:
    for f in sorted(glob.glob(ROOT+arm+'/cell_n7*.jsonl')):
        recs=[json.loads(l) for l in open(f,encoding='utf-8')]
        meta=recs[0]
        mi=[i for i,p in enumerate(meta['players']) if p.endswith('-magda')][0]
        mp=meta['players'][mi]; agent=meta['agents'][mi]
        games=collections.defaultdict(lambda: {'fetch':[], 'res':None, 'portal_bf':False,'portal_how':[]})
        pending=None
        for i,r in enumerate(recs):
            g=r.get('game')
            if g is None: continue
            G=games[g]
            if r['rec']=='entry' and r.get('type')=='STACK_RESOLVE' and r.get('card')=='Magda, Brazen Outlaw' and 'searches their library for an Artifact' in r.get('message',''):
                pending=(g,i)
                # find fetched card: look backwards/forwards within 40 recs for zone Library->Battlefield by magda
                got=None
                for j in list(range(i+1,min(i+40,len(recs))))+list(range(i-1,max(i-40,0),-1)):
                    z=recs[j]
                    if z.get('rec')=='zone' and z.get('game')==g and z.get('from')=='Library' and z.get('to')=='Battlefield' and z.get('toPlayer')==mp:
                        got=z['card']; break
                G['fetch'].append((r.get('turn') or 0, got))
            if r['rec']=='zone' and r.get('card')=='Portal to Phyrexia' and r.get('to')=='Battlefield' and r.get('toPlayer')==mp:
                G['portal_bf']=True; G['portal_how'].append(r.get('from'))
            if r['rec']=='result': G['res']=r
        for g,G in games.items():
            if G['res'] is None: continue
            out.append(dict(arm=arm,agent=agent,game=g,win=G['res']['winner']==mp,fetch=[x[1] for x in G['fetch']],portal=G['portal_bf'],how=G['portal_how']))
json.dump(out,open('magsearch.json','w'))
for arms,label in [(ARMS[:3],'lines3'),(ARMS[3:4],'nocombo'),(ARMS,'all5')]:
    print('=====',label)
    for agent in ['plan','stock']:
        S=[r for r in out if r['arm'] in arms and r['agent']==agent]
        srch=[r for r in S if r['fetch']]
        fetched=collections.Counter(c for r in S for c in r['fetch'])
        first=collections.Counter(r['fetch'][0] for r in srch)
        w=sum(r['win'] for r in srch); ns=[r for r in S if not r['fetch']]
        how=collections.Counter(h for r in S for h in r['how'])
        print(f"{agent}: games={len(S)} wins={sum(r['win'] for r in S)}  searched>=1: {len(srch)} games, won {w} ({100*w/max(1,len(srch)):.0f}%); no search: {len(ns)} games won {sum(r['win'] for r in ns)}")
        print('   portal_bf', sum(r['portal'] for r in S), 'via', dict(how))
        print('   all fetches', fetched.most_common(8))
        print('   first fetch', first.most_common(6))
    P=[r for r in out if r['arm'] in arms and r['agent']=='plan' and r['fetch']]
    Q=[r for r in out if r['arm'] in arms and r['agent']=='stock' and r['fetch']]
    a=sum(r['win'] for r in P); c=sum(r['win'] for r in Q)
    print('conditional on Magda searched: plan %d/%d vs stock %d/%d p=%.4f'%(a,len(P),c,len(Q),fisher(a,len(P)-a,c,len(Q)-c)))
