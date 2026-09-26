import json,glob,re,collections,os
os.chdir(r'C:/Users/Vatto/Magic Rules Engine/studies')
DIRS=['agent_viability/runs_015_default','agent_viability/runs_016_engine','agent_viability/runs_winmax','agent_viability/runs_nocombo','agent_viability/runs_pilot','behavior_rubric/runs_agent','behavior_rubric/runs_agent_093','behavior_rubric/runs_agent_shipping','human_ceiling/runs']
LM={"Gaea's Cradle","Bloom Tender","Mana Vault","Faeburrow Elder","Chromatic Orrery"}
out=collections.Counter(); per_dir=collections.defaultdict(collections.Counter)
for d in DIRS:
  for f in sorted(glob.glob(d+'/*.jsonl')):
    E=collections.defaultdict(list); meta=None
    for l in open(f,encoding='utf-8'):
        try: r=json.loads(l)
        except: continue
        if r.get('rec')=='meta' and meta is None: meta=r
        if r.get('rec')=='entry': E[r['game']].append(r)
    agents=dict(zip(meta.get('players',[]),meta.get('agents',[]))) if meta else {}
    for g,es in E.items():
        tapped={}  # name -> tapped (by mana entries within the turn)
        last_emiel=-99; derevi_p=None
        for i,e in enumerate(es):
            m=e['message']
            if e['type']=='TURN': tapped={}
            if e['type']=='MANA':
                mm=re.match(r"(.+?) \(\d+\) - \{T\}",m)
                if mm and mm.group(1) in LM: tapped[mm.group(1)]=True
            if e['type']=='STACK_ADD':
                mm=re.match(r"(\S+) activated Emiel the Blessed targeting \[Derevi",m)
                if mm: last_emiel=i; derevi_p=mm.group(1)
            if e['type']=='STACK_RESOLVE' and m.startswith('Whenever Derevi, Empyrial Tactician enters') and '[Zone Changer: Derevi' in m:
                if i-last_emiel>14: continue
                mt=re.search(r'\(Targeting: \[\[(.+?) \((\d+)\)\]\]\)',m)
                name=mt.group(1) if mt else None
                tl=[k for k,v in tapped.items() if v]
                key='tapped_linepiece' if tl else 'no_tapped_linepiece'
                hit = name in LM
                out[(key,'hit' if hit else 'miss')]+=1
                per_dir[d][(key,'hit' if hit else 'miss')]+=1
                out[('agent',agents.get(derevi_p),key,'hit' if hit else 'miss')]+=1
                if 'Gaea\'s Cradle' in tl: out[('cradle_tapped','hit_cradle' if name=="Gaea's Cradle" else 'miss')]+=1
                if hit and name in tapped: tapped[name]=False
for k,v in sorted(out.items(),key=str): print(k,v)
for d,c in per_dir.items(): print(d,dict(c))
