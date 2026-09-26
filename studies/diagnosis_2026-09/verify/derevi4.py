import json,glob,re,collections,os
os.chdir(r'C:/Users/Vatto/Magic Rules Engine/studies')
DIRS=['agent_viability/runs_015_default','agent_viability/runs_016_engine','agent_viability/runs_winmax','agent_viability/runs_nocombo','agent_viability/runs_pilot','behavior_rubric/runs_agent','behavior_rubric/runs_agent_093','behavior_rubric/runs_agent_shipping','human_ceiling/runs']
games=set(); wins=0; winturn=[]
allgames=0; dwins=0
for d in DIRS:
  for f in sorted(glob.glob(d+'/*.jsonl')):
    E=collections.defaultdict(list); res={}
    for l in open(f,encoding='utf-8'):
        try: r=json.loads(l)
        except: continue
        if r.get('rec')=='entry': E[r['game']].append(r)
        if r.get('rec')=='result': res[r['game']]=r
    for g,es in E.items():
        if g not in res: continue
        dp=[s['name'] for s in res[g]['seats'] if s['name'].endswith('-derevi')]
        if not dp: continue
        allgames+=1; dwins+= res[g]['winner']==dp[0]
        cradle_t=False; hit=False
        for e in es:
            m=e['message']
            if e['type']=='TURN': cradle_t=False
            if e['type']=='MANA' and m.startswith("Gaea's Cradle ("): cradle_t=True
            if e['type']=='STACK_ADD' and 'activated Emiel the Blessed targeting [Derevi' in m and cradle_t: hit=True
        if hit:
            games.add((f,g)); wins+= res[g]['winner']==dp[0]
print('derevi seat-games',allgames,'derevi wins',dwins)
print('games with Emiel-blink of Derevi after Cradle tapped same turn:',len(games),'derevi won',wins)
