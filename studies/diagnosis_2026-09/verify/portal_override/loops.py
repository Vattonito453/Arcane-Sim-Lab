import json, glob, collections
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ['runs_015_default','runs_winmax','runs_016_engine','runs_nocombo']
for arm in ARMS:
    for agent_want in ['plan','stock']:
        maxes=[]; tapmax=[]
        for f in sorted(glob.glob(ROOT+arm+'/cell_n7*.jsonl')):
            recs=[json.loads(l) for l in open(f,encoding='utf-8')]
            meta=recs[0]; mi=[i for i,p in enumerate(meta['players']) if p.endswith('-magda')][0]
            mp=meta['players'][mi]
            if meta['agents'][mi]!=agent_want: continue
            per=collections.defaultdict(collections.Counter); win={}
            for r in recs:
                if r['rec']=='zone' and r.get('to')=='Battlefield' and r.get('toPlayer')==mp and r.get('token'):
                    per[r['game']][r.get('turn')]+=1
                if r['rec']=='result': win[r['game']]=r['winner']==mp
            for g in win:
                m=max(per[g].values()) if per[g] else 0
                maxes.append((m,win[g]))
        big=[x for x in maxes if x[0]>=40]
        print(arm, agent_want, 'games',len(maxes),'games with >=40 tokens in one turn:',len(big),'won',sum(w for _,w in big), 'top', sorted(maxes,reverse=True)[:5])
