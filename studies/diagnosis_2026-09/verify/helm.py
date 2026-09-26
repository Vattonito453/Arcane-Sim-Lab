import json,glob,re,collections,os
os.chdir(r'C:/Users/Vatto/Magic Rules Engine/studies')
res=collections.defaultdict(collections.Counter)
allrows=[]
for f in glob.glob('**/*.jsonl',recursive=True):
    try: txt=open(f,encoding='utf-8').read()
    except: continue
    if 'Helm of the Host' not in txt or 'Godo, Bandit Warlord' not in txt: continue
    d=os.path.dirname(f)
    games=collections.defaultdict(lambda: {'zones':[], 'attach':[], 'entries':[], 'result':None})
    meta=None
    for l in txt.splitlines():
        try: r=json.loads(l)
        except: continue
        rec=r.get('rec')
        if rec=='meta': meta=r; continue
        g=r.get('game')
        if rec=='zone': games[g]['zones'].append(r)
        elif rec=='attach': games[g]['attach'].append(r)
        elif rec=='entry': games[g]['entries'].append(r)
        elif rec=='result': games[g]['result']=r
    agents=dict(zip(meta.get('players',[]),meta.get('agents',[]))) if meta else {}
    for g,G in games.items():
        if G['result'] is None: continue
        # battlefield tracking by turn: helm & godo controllers
        on=collections.defaultdict(set)  # cardname -> set of controllers ever on bf
        bf={}
        both=False; helm_ids=set(); godo_ctrl=None
        for z in G['zones']:
            if z['to']=='Battlefield':
                bf[z['cardId']]=(z['card'],z.get('toPlayer'))
            elif z['from']=='Battlefield':
                bf.pop(z['cardId'],None)
            names={}
            for cid,(n,p) in bf.items():
                if n in('Helm of the Host','Godo, Bandit Warlord') and not (n=='Godo, Bandit Warlord' and False):
                    names.setdefault(n,set()).add(p)
            if 'Helm of the Host' in names and 'Godo, Bandit Warlord' in names:
                common=names['Helm of the Host']&names['Godo, Bandit Warlord']
                if common:
                    both=True; godo_ctrl=sorted(common)[0]
        if not both: continue
        att=[a.get('to') for a in G['attach'] if a['card']=='Helm of the Host']
        cat='godo' if 'Godo, Bandit Warlord' in att else ('elsewhere' if any(att) else 'never')
        # combats per turn for godo ctrl
        maxc=0; cur=0
        for e in G['entries']:
            m=e.get('message','')
            if e.get('type')=='TURN': cur=0
            if e.get("type")=="PHASE" and m.endswith("Beginning of Combat Step") and (godo_ctrl+"'") in m:
                cur+=1; maxc=max(maxc,cur)
        won=G['result'].get('winner')==godo_ctrl
        allrows.append((d,f,g,godo_ctrl,agents.get(godo_ctrl),cat,maxc,won))
tot=collections.Counter(); 
for row in allrows:
    d,f,g,p,ag,cat,maxc,won=row
    res[d][cat]+=1; tot[cat]+=1
    if cat=='godo':
        tot['godo_4plus']+= maxc>=4; tot['godo_4plus_won']+= (maxc>=4 and won); tot['godo_won']+=won
    tot['won_'+cat]+=won
    tot['agent_'+str(ag)+'_'+cat]+=1
for d,c in sorted(res.items()): print(d,dict(c))
print('TOTAL seat-games',len(allrows),dict(tot))
json.dump(allrows,open(r'C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad/diagnosis/verify/helm_rows.json','w'))
