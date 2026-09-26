import json,glob,collections
ROOT="C:/Users/Vatto/Magic Rules Engine/studies/"
SETS=['behavior_rubric/runs_agent_093','human_ceiling/runs','behavior_rubric/runs_agent_shipping','agent_viability/runs_015_default','agent_viability/runs_016_engine','agent_viability/runs_winmax']
EX=("Demonic Consultation","Tainted Pact")
res=collections.Counter(); cons=collections.Counter()
for s in SETS:
  for f in glob.glob(ROOT+s+'/*.jsonl'):
    meta=None; Z=collections.defaultdict(list); W={}; O=collections.defaultdict(list)
    for l in open(f,encoding='utf-8'):
        try: r=json.loads(l)
        except: continue
        if r.get('rec')=='meta': meta=r
        elif r.get('rec')=='zone': Z[r['game']].append(r)
        elif r.get('rec')=='result': W[r['game']]=r.get('winner')
        elif r.get('type')=='GAME_OUTCOME': O[r['game']].append(r['message'])
    if meta is None: continue
    ag=dict(zip(meta['players'],meta.get('agents',['stock']*4)))
    for g,zs in Z.items():
        zs.sort(key=lambda r:r['turn'])
        hand=collections.defaultdict(set); lib=collections.defaultdict(set); stk=collections.defaultdict(set)
        oracle_win = any("Thassa's Oracle" in m for m in O[g])
        for r in zs:
            fp,tp,c=r.get('fromPlayer'),r.get('toPlayer'),r['card']
            if r['from']=='Hand' and fp: hand[fp].discard(c)
            if r['to']=='Hand' and tp: hand[tp].add(c)
            if r['to']=='Stack' and fp: stk[(fp,r['turn'])].add(c)
            if c=="Thassa's Oracle" and r['to']=='Stack' and fp:
                pre=[x for x in EX if x in stk[(fp,r['turn'])]]
                had=[x for x in EX if x in hand[fp]]
                k=(s.split('/')[-1] if False else '', ag.get(fp), 'exile spell cast first this turn' if pre else ('exile spell IN HAND, Oracle cast anyway' if had else 'no exile spell'), 'won by Oracle' if (W.get(g)==fp and oracle_win) else 'no Oracle win')
                res[k]+=1
            if c in EX and r['to']=='Stack' and fp:
                oracle_in_hand = "Thassa's Oracle" in hand[fp]
                cons[(ag.get(fp), c, 'Oracle in hand' if oracle_in_hand else 'no Oracle in hand')]+=1
for k,v in sorted(res.items(), key=lambda x:-x[1]): print(v,k)
print('--- exile-spell casts')
for k,v in sorted(cons.items(), key=lambda x:-x[1]): print(v,k)
