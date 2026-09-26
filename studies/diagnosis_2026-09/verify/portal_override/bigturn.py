import json, glob, collections
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
for arm in ['runs_015_default','runs_016_engine','runs_nocombo']:
  for f in sorted(glob.glob(ROOT+arm+'/cell_n7*.jsonl')):
    recs=[json.loads(l) for l in open(f,encoding='utf-8')]
    meta=recs[0]; mi=[i for i,p in enumerate(meta['players']) if p.endswith('-magda')][0]; mp=meta['players'][mi]
    per=collections.defaultdict(collections.Counter); names=collections.defaultdict(collections.Counter)
    bf=collections.defaultdict(collections.Counter); snap={}
    win={}
    for r in recs:
        if r['rec']=='zone':
            g=r['game']
            if r.get('to')=='Battlefield' and r.get('toPlayer')==mp:
                if r.get('token'): per[g][r['turn']]+=1; names[(g,r['turn'])][r['card']]+=1
                else: bf[g][r['card']]+=1
            if r.get('from')=='Battlefield' and r.get('fromPlayer')==mp and not r.get('token'):
                bf[g][r['card']]-=1
            if per[g] and per[g][r['turn']]==40: snap[(g,r['turn'])]={k for k,v in bf[g].items() if v>0}
        if r['rec']=='result': win[r['game']]=r['winner']==mp
    for (g,t),s in snap.items():
        print(arm, meta['agents'][mi], f.split('_')[-1], 'g',g,'t',t,'win',win.get(g),'tokens',dict(names[(g,t)].most_common(3)), 'Clock' in ' '.join(s), 'Portal' in ' '.join(s), sorted(x for x in s if x in ('Clock of Omens','Liquimetal Torque','Universal Automaton','Adaptive Automaton','Metallic Mimic','Roaming Throne','Barkform Harvester','Three Tree Mascot','Battered Golem','Maskwood Nexus','Stalactite Dagger','Magda, Brazen Outlaw','Portal to Phyrexia')))
