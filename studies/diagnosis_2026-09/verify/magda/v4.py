import json, glob, collections, re, statistics
BASE = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ["runs_015_default", "runs_winmax", "runs_016_engine"]
MAG = "Ai(1)-magda"
gaps=[]; kill=collections.Counter(); portal_rounds=[]
for arm in ARMS:
    for f in sorted(glob.glob(BASE + arm + "/cell_n7*.jsonl")):
        games = collections.defaultdict(lambda: dict(portal=None, lastdmg={}, killed={}, winner=None, turns=None, turn=0))
        mp=None
        for line in open(f, encoding='utf-8'):
            try: r = json.loads(line)
            except: continue
            rec=r.get('rec')
            if rec=='meta': mp = r['players'][r['agents'].index('plan')]==MAG; continue
            G=games[r.get('game')]
            if rec=='zone' and r.get('card')=='Portal to Phyrexia' and r.get('to')=='Battlefield' and r.get('toPlayer')==MAG and G['portal'] is None:
                G['portal']=r.get('turn')
            elif rec=='entry':
                t=r['type']; m=r['message']
                if t=='TURN':
                    mm=re.match(r'Turn (\d+)',m); G['turn']=int(mm.group(1)) if mm else G['turn']
                if t=='DAMAGE':
                    mm=re.search(r'deals (\d+) (combat|non-combat) damage to (Ai\(\d\)-\S+)\.', m)
                    if mm: G['lastdmg'][mm.group(3)]=mm.group(2)
                if t=='LIFE':
                    mm=re.match(r'Life: (Ai\(\d\)-\S+) (-?\d+) > (-?\d+)', m)
                    if mm and int(mm.group(3))<=0 and mm.group(1) not in G['killed']:
                        G['killed'][mm.group(1)]=G['lastdmg'].get(mm.group(1),'life-loss')
            elif rec=='result':
                G['winner']=r.get('winner'); G['turns']=r.get('turns')
        for g,G in games.items():
            if mp or G['winner']!=MAG or G['portal'] is None: continue
            gaps.append((G['turns']-G['portal'])/4); portal_rounds.append(G['portal']/4)
            for p,how in G['killed'].items():
                if p!=MAG: kill[how]+=1
print("stock Magda wins with Portal:", len(gaps), "median rounds Portal->end", statistics.median(gaps), "median portal round", statistics.median(portal_rounds))
print("how opponents died (last damage type before life<=0):", kill)
