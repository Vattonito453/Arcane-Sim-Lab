"""Classify every PLAN Thassa's Oracle cast: was a Consultation cast in response
to its ETB trigger; if not, was Consultation / Tainted Pact in hand when the
Oracle was cast (zone records), and was the cast chosen by combo_cast or stock."""
import collections, glob, json, re
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
SETS = ["agent_viability/runs_015_default/cell_*.jsonl","agent_viability/runs_winmax/cell_*.jsonl","agent_viability/runs_016_engine/cell_*.jsonl","behavior_rubric/runs_agent_shipping/*.jsonl","tutor_targeting/runs_stage2/*.jsonl","behavior_rubric/runs_agent_093/*.jsonl","behavior_rubric/runs_agent/*.jsonl"]
res = collections.Counter()
later = collections.Counter()
for pat in SETS:
    for f in glob.glob(S+pat):
        meta=None; E=collections.defaultdict(list); Z=collections.defaultdict(list); A=collections.defaultdict(list)
        for l in open(f,encoding='utf-8'):
            try: r=json.loads(l)
            except: continue
            k=r.get('rec')
            if k=='meta': meta=r
            elif k=='entry': E[r['game']].append(r)
            elif k=='zone': Z[r['game']].append(r)
            elif k=='agent': A[r['game']].append(r)
        if not meta: continue
        agents=dict(zip(meta['players'],meta['agents']))
        plans=[p for p,a in agents.items() if a=='plan']
        for g,es in E.items():
            es.sort(key=lambda r:r['seq'])
            for P in plans:
                # entry-level: per Oracle cast, in-response Consultation?
                casts=[]; open_idx=None
                for e in es:
                    m=e['message']
                    if e['type']=='STACK_ADD' and m.startswith(P+" cast Thassa's Oracle"):
                        casts.append({'resp':False,'trig':False})
                    elif e['type']=='STACK_ADD' and m.startswith(P+" triggered Thassa's Oracle") and casts:
                        casts[-1]['trig']=True; open_idx=len(casts)-1
                    elif e['type']=='STACK_RESOLVE' and m.startswith("When Thassa's Oracle enters"):
                        open_idx=None
                    elif e['type']=='STACK_ADD' and m.startswith(P+" cast Demonic Consultation") and open_idx is not None:
                        casts[open_idx]['resp']=True
                # zone-level: hand contents at each Oracle Hand->Stack
                hand=collections.Counter(); k=0; turns=[]
                for z in Z[g]:
                    c=z['card']
                    if z.get('toPlayer')==P and z['to']=='Hand': hand[c]+=1
                    if z.get('fromPlayer')==P and z['from']=='Hand': hand[c]-=1
                    if c=="Thassa's Oracle" and z['from']=='Hand' and z['to']=='Stack' and z.get('fromPlayer')==P:
                        if k<len(casts):
                            casts[k]['consult_in_hand']=hand["Demonic Consultation"]>0
                            casts[k]['pact_in_hand']=hand["Tainted Pact"]>0
                            casts[k]['turn']=z['turn']
                        k+=1
                cc_turns=collections.Counter(a['turn'] for a in A[g] if a['player']==P and a['event']=='combo_cast' and a['detail'].startswith("Thassa's Oracle"))
                for c in casts:
                    if 'turn' not in c: 
                        res[('unaligned',)]+=1; continue
                    by = 'combo_cast' if cc_turns.get(c['turn'],0)>0 else 'stock'
                    if cc_turns.get(c['turn'],0)>0: cc_turns[c['turn']]-=1
                    if c['resp']: key=('consult_in_response', by)
                    elif not c['trig']: key=('no_ETB_trigger_logged', by, 'consult_in_hand' if c['consult_in_hand'] else '-')
                    else:
                        key=('ETB_spent', by, 'consult_in_hand' if c['consult_in_hand'] else ('pact_in_hand' if c['pact_in_hand'] else 'no_piece_in_hand'))
                    res[key]+=1
tot=sum(res.values())
print("plan Oracle casts:", tot)
for k,v in sorted(res.items(), key=lambda kv:-kv[1]): print(f"{v:4d} {k}")
