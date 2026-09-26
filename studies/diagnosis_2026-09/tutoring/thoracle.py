import json,glob,re,collections,os
out=collections.Counter(); ex=[]
for arm in ['agent_viability/runs_015_default','agent_viability/runs_winmax','agent_viability/runs_016_engine','behavior_rubric/runs_agent_shipping']:
    for f in glob.glob(arm+'/*.jsonl'):
        meta=None; games=collections.defaultdict(list)
        for line in open(f,encoding='utf-8'):
            try: r=json.loads(line)
            except: continue
            if r.get('rec')=='meta': meta=r; continue
            if r.get('rec') in ('zone','entry','result'): games[r.get('game')].append(r)
        if not meta: continue
        ag=dict(zip(meta['players'],meta['agents']))
        for g,recs in games.items():
            for p,a in ag.items():
                cons=[r for r in recs if r.get('rec')=='zone' and r['card']=='Demonic Consultation' and r['from']=='Hand' and r['to']=='Stack' and r['fromPlayer']==p]
                if not cons: continue
                orc=[r for r in recs if r.get('rec')=='zone' and r['card']=="Thassa's Oracle" and r['to']=='Battlefield' and r.get('toPlayer')==p]
                res=[r for r in recs if r.get('rec')=='result']
                won=bool(res) and res[0]['winner']==p
                lost_msgs=[r['message'] for r in recs if r.get('rec')=='entry' and r['type']=='GAME_OUTCOME' and p in r['message']]
                cres=[r['message'][:170] for r in recs if r.get('rec')=='entry' and r['type']=='STACK_RESOLVE' and r.get('card')=='Demonic Consultation']
                last_or=[o['turn'] for o in orc if o['turn']<=cons[0]['turn']]; key=(a, ('oracle SAME turn as Consultation' if last_or and last_or[-1]==cons[0]['turn'] else ('oracle EARLIER turn' if last_or else ('oracle later/never'))), 'WON' if won else 'lost', lost_msgs[0].split(' has ')[1][:45] if lost_msgs else '')
                out[key]+=1
                if len(ex)<16: ex.append((os.path.basename(f)[-28:],g,p,a,'cons',cons[0]['turn'],'oracle',[o['turn'] for o in orc],'won' if won else 'lost',lost_msgs[:1],cres[:1]))
for k,v in sorted(out.items()): print(v,k)
for e in ex: print(e)
