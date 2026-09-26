import json,glob,re,collections,os,sys
os.chdir(r'C:/Users/Vatto/Magic Rules Engine/studies')
LINE_MANA={"Gaea's Cradle","Bloom Tender","Mana Vault","Faeburrow Elder","Chromatic Orrery"}
files=[f for f in glob.glob('**/*.jsonl',recursive=True)]
tot=collections.Counter(); bydir=collections.defaultdict(collections.Counter)
tgt_etb=collections.Counter()
cond=collections.Counter()
emiel_blinks=collections.Counter()
for f in files:
    try:
        txt=open(f,encoding='utf-8').read()
    except Exception: continue
    if 'Derevi, Empyrial Tactician' not in txt: continue
    d=os.path.dirname(f)
    owner={}
    bf=collections.defaultdict(dict)  # game -> cardId -> (name, controller)
    pending={}
    for l in txt.splitlines():
        try: r=json.loads(l)
        except: continue
        g=r.get('game')
        if r.get('rec')=='zone':
            cid=r.get('cardId'); key=(g,cid)
            if key not in owner and r.get('fromPlayer'): owner[key]=r['fromPlayer']
            if r.get('to')=='Battlefield': bf[g][cid]=(r['card'],r.get('toPlayer'))
            elif r.get('from')=='Battlefield': bf[g].pop(cid,None)
            continue
        if r.get('rec')!='entry': continue
        m=r.get('message','')
        if r.get('type')=='STACK_ADD' and 'activated Emiel the Blessed targeting [Derevi' in m:
            emiel_blinks[d]+=1
        if r.get('type')=='STACK_RESOLVE' and m.startswith('Whenever Derevi, Empyrial Tactician enters'):
            mt=re.search(r'\(Targeting: \[\[(.+?) \((\d+)\)\]\]\)',m)
            cause='etb' if '[Zone Changer: Derevi' in m else ('combat' if 'Damage Source' in m else 'other')
            p=None
            tot['resolve']+=1; bydir[d]['resolve']+=1
            if not mt:
                bydir[d]['notarget']+=1; continue
            name,cid=mt.group(1),int(mt.group(2))
            # derevi controller: find from bf
            derevi_ctrl=None
            for c,(n,pl) in bf[g].items():
                if n=='Derevi, Empyrial Tactician': derevi_ctrl=pl
            own=owner.get((g,cid))
            ctrl=bf[g].get(cid,(None,None))[1]
            mine = (ctrl==derevi_ctrl) if ctrl else (own==derevi_ctrl)
            cat='cradle' if name=="Gaea's Cradle" else ('linemana' if name in LINE_MANA else ('own_other' if mine else 'opp'))
            bydir[d][cause+':'+cat]+=1; tot[cause+':'+cat]+=1
            cradle_on = any(n=="Gaea's Cradle" and pl==derevi_ctrl for n,pl in bf[g].values())
            lm_on = any(n in LINE_MANA and pl==derevi_ctrl for n,pl in bf[g].values())
            emiel_on = any(n=='Emiel the Blessed' and pl==derevi_ctrl for n,pl in bf[g].values())
            if cause=='etb':
                cond[('etb','cradle_on' if cradle_on else 'no_cradle','emiel_on' if emiel_on else 'no_emiel',cat)]+=1
                if lm_on and emiel_on: cond[('etb_with_emiel_and_linemana',cat)]+=1
            if cause=='etb': tgt_etb[name]+=1
        if r.get('type')=='STACK_ADD' and 'triggered Derevi, Empyrial Tactician' in m:
            tot['add']+=1; bydir[d]['add']+=1
for d,c in sorted(bydir.items()): print(d,dict(c))
print('TOTAL',dict(tot))
print('emiel blinks derevi',dict(emiel_blinks),sum(emiel_blinks.values()))
for k,v in sorted(cond.items(),key=lambda x:str(x[0])): print(k,v)
print('ETB targets',tgt_etb.most_common(25))
