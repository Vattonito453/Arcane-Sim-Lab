import json, glob, collections
S=r"C:/Users/Vatto/Magic Rules Engine/studies/"
for label,pat in [('hc_runs',S+'human_ceiling/runs/shim_raw_hc_*.jsonl'),('tt_stock',S+'tutor_targeting/runs_stock/*.jsonl'),('tt_stage0',S+'tutor_targeting/runs/*.jsonl')]:
    y=[0,0]; n=[0,0]; agents=set()
    for f in sorted(glob.glob(pat)):
        recs=[json.loads(l) for l in open(f,encoding='utf-8')]
        meta=recs[0]
        mis=[i for i,p in enumerate(meta['players']) if 'magda' in p.lower()]
        if not mis: continue
        mi=mis[0]; mp=meta['players'][mi]; agents.add(meta['agents'][mi] if 'agents' in meta else '?')
        portal=collections.defaultdict(bool); res={}
        for r in recs:
            if r['rec']=='zone' and r.get('card')=='Portal to Phyrexia' and r.get('to')=='Battlefield' and r.get('toPlayer')==mp: portal[r['game']]=True
            if r['rec']=='result': res[r['game']]=r['winner']==mp
        for g,w in res.items():
            t=y if portal[g] else n; t[0]+=w; t[1]+=1
    print(label, 'agents',agents,'portal: %d/%d'%tuple(y),'no portal: %d/%d'%tuple(n))
