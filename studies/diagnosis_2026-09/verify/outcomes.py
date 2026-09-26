import json,glob,collections,re,sys
ROOT="C:/Users/Vatto/Magic Rules Engine/studies/"
SETS=['behavior_rubric/runs_agent_093','human_ceiling/runs','behavior_rubric/runs_agent_shipping','agent_viability/runs_015_default','agent_viability/runs_016_engine','agent_viability/runs_winmax']
tot=collections.Counter()
for s in SETS:
    c=collections.Counter(); deck=[]
    for f in glob.glob(ROOT+s+'/*.jsonl'):
        G=collections.defaultdict(list); res={}
        for l in open(f,encoding='utf-8'):
            try: r=json.loads(l)
            except: continue
            if r.get('type')=='GAME_OUTCOME': G[r['game']].append(r['message'])
            if r.get('rec')=='result': res[r['game']]=r
        for g,r in res.items():
            ms=G.get(g,[])
            spell=[re.search(r"'(.+)'",m).group(1) for m in ms if 'by spell' in m or 'due to effect' in m]
            dk=[m for m in ms if 'empty library' in m]
            if spell: c['spell:'+spell[0]]+=1
            if dk:
                c['deckout-loss-games']+=1; deck.append((f.split('/')[-1],g,r.get('winner'),dk, len([m for m in ms if 'has lost' in m])))
            c['games']+=1
    print(s,dict(c))
    for x in deck: print('    ',x)
    tot.update(c)
print('TOTAL',dict(tot))
