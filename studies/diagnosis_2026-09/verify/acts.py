import json,glob,collections,re
ROOT="C:/Users/Vatto/Magic Rules Engine/studies/"
SETS=['behavior_rubric/runs_agent_093','human_ceiling/runs','behavior_rubric/runs_agent_shipping','agent_viability/runs_015_default','agent_viability/runs_016_engine','agent_viability/runs_winmax']
P=["Emiel the Blessed","Clock of Omens","Kiki-Jiki, Mirror Breaker","Basalt Monolith","Grinding Station","Devoted Druid","Transmutation Font","Lion's Eye Diamond","Zealous Conscripts","Underworld Breach","Brain Freeze","Walking Ballista","Academy Manufactor","Magda, Brazen Outlaw"]
TURN=re.compile(r"^Turn (\d+) ")
arr=collections.Counter(); act=collections.Counter(); mana=collections.Counter(); trig=collections.Counter(); cast=collections.Counter()
mx=collections.Counter(); games=0
for s in SETS:
  for f in glob.glob(ROOT+s+'/*.jsonl'):
    per=collections.Counter(); cur=collections.defaultdict(int)
    for l in open(f,encoding='utf-8'):
        try: r=json.loads(l)
        except: continue
        g=r.get('game')
        if r.get('rec')=='result': games+=1
        if r.get('rec')=='zone' and r['to']=='Battlefield' and r['card'] in P: arr[r['card']]+=1
        if r.get('rec')!='entry': continue
        t=r['type']; m=r['message']
        if t=='TURN':
            mm=TURN.match(m); cur[g]=int(mm.group(1)) if mm else cur[g]
        if t=='STACK_ADD':
            mm=re.match(r'^(Ai\(\d\)-\S+) (activated|triggered|cast) (.+?)(?: targeting .*)?$',m,re.S)
            if mm and mm.group(3) in P:
                k=mm.group(2)
                if k=='activated': act[mm.group(3)]+=1; per[(g,cur[g],mm.group(3))]+=1
                elif k=='triggered': trig[mm.group(3)]+=1
                else: cast[mm.group(3)]+=1
        if t=='MANA':
            for p in P:
                if m.startswith(p+' ('): mana[p]+=1
    for (g,tt,c),v in per.items(): mx[c]=max(mx[c],v)
print('games',games)
print('%-28s %8s %8s %8s %8s %8s %8s'%('card','arrive','cast','activ','maxturn','trig','manaAb'))
for p in P: print('%-28s %8d %8d %8d %8d %8d %8d'%(p,arr[p],cast[p],act[p],mx[p],trig[p],mana[p]))
