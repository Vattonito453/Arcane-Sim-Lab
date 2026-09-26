import json, re, sys, collections
from pathlib import Path
BASE=Path(r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability")
arms=sys.argv[1:] or ['runs_015_default','runs_winmax','runs_016_engine','runs_nocombo','runs_pilot']
CAST=re.compile(r"^(Ai\(\d\)-\S+) cast (.+)$")
tot=collections.Counter()
rows=[]
for arm in arms:
    for f in sorted((BASE/arm).glob('cell_*.jsonl')):
        meta=None; games={}
        for line in open(f,encoding='utf-8'):
            r=json.loads(line)
            rec=r.get('rec')
            if rec=='meta': meta=r; continue
            g=r.get('game')
            if g is None: continue
            G=games.setdefault(g,{'turn':0,'casts':[],'outcome':[],'result':None})
            if rec=='entry':
                t=r.get('type'); m=r.get('message','')
                if t=='TURN':
                    mm=re.match(r'Turn (\d+)',m)
                    if mm: G['turn']=int(mm.group(1))
                elif t=='STACK_ADD':
                    mm=CAST.match(m)
                    if mm and mm.group(2) in ("Demonic Consultation","Thassa's Oracle","Tainted Pact"):
                        G['casts'].append((G['turn'],mm.group(1),mm.group(2),r['seq']))
                elif t=='GAME_OUTCOME':
                    G['outcome'].append(m)
            elif rec=='result':
                G['result']=r
        agent_of={p:a for p,a in zip(meta['players'],meta['agents'])}
        for g,G in games.items():
            byp=collections.defaultdict(list)
            for c in G['casts']: byp[c[1]].append(c)
            for p,cs in byp.items():
                ag=agent_of[p]
                for c in cs: tot[(arm,ag,c[2])]+=1
                cons=[c for c in cs if c[2]=='Demonic Consultation']
                ora=[c for c in cs if c[2]=="Thassa's Oracle"]
                for c in cons:
                    same=[o for o in ora if o[0]==c[0]]
                    earlier=[o for o in ora if o[0]<c[0]]
                    res=G['result']
                    won = res and res.get('winner')==p
                    decked=any(m.startswith(p) and 'empty library' in m for m in G['outcome'])
                    oraclewin=any(m.startswith(p) and "won due to effect of 'Thassa's Oracle'" in m for m in G['outcome'])
                    rows.append(dict(arm=arm,cell=f.name,game=g,player=p,agent=ag,turn=c[0],same=bool(same),earlier=bool(earlier),
                        later=bool([o for o in ora if o[0]>c[0]]),won=bool(won),decked=decked,oraclewin=oraclewin,
                        timedout=bool(res and (res.get('timedOut') or res.get('draw') or res.get('turnCapped'))), noresult=res is None))
print("cast totals by (arm, agent, card):")
for k,v in sorted(tot.items()): print(' ',k,v)
plan=[r for r in rows if r['agent']=='plan']
print('\nConsultation casts: plan',len(plan),' stock',len([r for r in rows if r['agent']=='stock']))
def summ(rs,label):
    print(f"{label}: n={len(rs)} won={sum(r['won'] for r in rs)} oraclewin={sum(r['oraclewin'] for r in rs)} lost={sum((not r['won']) and not r['timedout'] and not r['noresult'] for r in rs)} decked={sum(r['decked'] for r in rs)} timedout/draw={sum(r['timedout'] for r in rs)} noresult={sum(r['noresult'] for r in rs)}")
summ(plan,'plan all')
summ([r for r in plan if r['same']],'plan Oracle same turn')
summ([r for r in plan if r['earlier'] and not r['same']],'plan Oracle earlier turn only')
summ([r for r in plan if not r['same'] and not r['earlier']],'plan no Oracle same/earlier')
summ([r for r in plan if not r['same'] and not r['earlier'] and not r['later']],'plan no Oracle at all that game')
for a in arms:
    summ([r for r in plan if r['arm']==a],'  arm '+a)
# per-deck
print()
for r in plan:
    print(r['arm'][5:],r['cell'][5:-6],'g',r['game'],r['player'][6:],'t',r['turn'],'same' if r['same'] else ('earlier' if r['earlier'] else ('later' if r['later'] else 'none')),'WON' if r['won'] else '', 'ORACLEWIN' if r['oraclewin'] else '', 'DECKED' if r['decked'] else '', 'TO' if r['timedout'] else '')
