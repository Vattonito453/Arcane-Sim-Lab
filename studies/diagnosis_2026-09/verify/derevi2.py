import json,glob,re,collections,os
os.chdir(r'C:/Users/Vatto/Magic Rules Engine/studies')
ZP={'':-1,'UNTAP':0,'UPKEEP':1,'DRAW':2,'MAIN1':3,'COMBAT_BEGIN':4,'COMBAT_DECLARE_ATTACKERS':5,'COMBAT_DECLARE_BLOCKERS':6,'COMBAT_FIRST_STRIKE_DAMAGE':7,'COMBAT_DAMAGE':8,'COMBAT_END':9,'MAIN2':10,'END_OF_TURN':11,'CLEANUP':12}
EP=[('Untap step',0),('Upkeep step',1),('Draw step',2),('Main phase, precombat',3),('Beginning of Combat Step',4),('Declare Attackers Step',5),('Declare Blockers Step',6),('First Strike Damage Step',7),('Combat Damage Step',8),('End of Combat Step',9),('Main phase, postcombat',10),('End step',11),('Cleanup step',12)]
LINE_MANA={"Gaea's Cradle","Bloom Tender","Mana Vault","Faeburrow Elder","Chromatic Orrery"}
DIRS=['agent_viability/runs_015_default','agent_viability/runs_016_engine','agent_viability/runs_winmax']
out=collections.Counter(); samples=[]
for d in DIRS:
  for f in sorted(glob.glob(d+'/*.jsonl')):
    meta=None; E=collections.defaultdict(list); Z=collections.defaultdict(list)
    for l in open(f,encoding='utf-8'):
        try: r=json.loads(l)
        except: continue
        if r.get('rec')=='meta' and meta is None: meta=r
        if r.get('rec')=='entry': E[r['game']].append(r)
        elif r.get('rec')=='zone': Z[r['game']].append(r)
    agents=dict(zip(meta.get('players',[]),meta.get('agents',[]))) if meta else {}
    for g in E:
        zs=Z[g]; zi=0; bf={}
        turn=0; ph=0; last_emiel=-99
        for idx,e in enumerate(E[g]):
            m=e.get('message','')
            if e['type']=='TURN':
                mm=re.match(r'Turn (\d+)',m); turn=int(mm.group(1)); ph=0
            elif e['type']=='PHASE':
                for k,v in EP:
                    if m.endswith(k): ph=v
            # advance zone state to (turn,ph)
            while zi<len(zs) and (zs[zi]['turn'],ZP.get(zs[zi].get('phase',''),-1))<=(turn,ph):
                z=zs[zi]; zi+=1
                if z['to']=='Battlefield': bf[z['cardId']]=(z['card'],z['toPlayer'])
                elif z['from']=='Battlefield': bf.pop(z['cardId'],None)
            if e['type']=='STACK_ADD' and 'activated Emiel the Blessed targeting [Derevi' in m: last_emiel=idx
            if e['type']=='STACK_RESOLVE' and m.startswith('Whenever Derevi, Empyrial Tactician enters'):
                mt=re.search(r'\(Targeting: \[\[(.+?) \((\d+)\)\]\]\)',m)
                etb='[Zone Changer: Derevi' in m
                ctrl=None
                for n,p in bf.values():
                    if n=='Derevi, Empyrial Tactician': ctrl=p
                if ctrl is None:
                    mm=re.search(r'(Ai\(\d\)-derevi)',f+str(meta.get('players')))
                    ctrl=[p for p in meta['players'] if p.endswith('-derevi')][0]
                via_emiel = etb and idx-last_emiel<12
                name=mt.group(1) if mt else None; cid=int(mt.group(2)) if mt else None
                tctrl=bf.get(cid,(None,None))[1]
                cat='none' if not mt else ('cradle' if name=="Gaea's Cradle" else ('linemana' if name in LINE_MANA else ('own' if tctrl==ctrl else ('opp' if tctrl else 'unk'))))
                cradle_on=any(n=="Gaea's Cradle" and p==ctrl for n,p in bf.values())
                lm_on=[n for n,p in bf.values() if n in LINE_MANA and p==ctrl]
                emiel_on=any(n=='Emiel the Blessed' and p==ctrl for n,p in bf.values())
                ag=agents.get(ctrl)
                out[('all',cat)]+=1
                out[('cause','etb_emiel' if via_emiel else ('etb_other' if etb else 'combat'),cat)]+=1
                if via_emiel:
                    out[('emielblink','cradle_on' if cradle_on else 'no_cradle',cat)]+=1
                    out[('emielblink','linemana_on' if lm_on else 'no_linemana',cat)]+=1
                    out[('emielblink_agent',ag,cat)]+=1
                    if lm_on: samples.append((os.path.basename(f),g,e['seq'],turn,ag,lm_on,name))
for k,v in sorted(out.items(),key=lambda x:str(x[0])): print(k,v)
print(len(samples))
for s in samples[:60]: print(s)
