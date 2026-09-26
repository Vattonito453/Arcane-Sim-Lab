"""Which cards does STOCK Forge actually convert? For each deck, over stock seats
in agent_viability (4 arms incl. nocombo), P(win | card resolved for this seat,
i.e. reached battlefield or was cast) vs P(win | not), min 12 games with.
Compare to the plan's search-target value for that card."""
import json, glob, re, collections
from pathlib import Path
S=Path(r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability")
plans={}
for pod in ('n7WpsqsZtdQ','2iA_Jt0d6sM'):
    plans.update(json.load(open(S/'runs_015_default'/f'plans_{pod}.json',encoding='utf-8'))['decks'])
stats=collections.defaultdict(lambda: collections.Counter())
games_per=collections.Counter(); wins_per=collections.Counter()
for arm in ('runs_015_default','runs_winmax','runs_016_engine','runs_nocombo'):
    for fn in glob.glob(str(S/arm/'cell_*.jsonl')):
        meta=None; games=collections.defaultdict(lambda:{'res':set(),'r':None})
        for line in open(fn,encoding='utf-8'):
            try: r=json.loads(line)
            except: continue
            if r.get('rec')=='meta': meta=r
            elif r.get('rec')=='zone':
                if r['to'] in ('Battlefield','Stack') and r['from'] in ('Hand','Library','Command','Graveyard','Exile'):
                    p=r.get('toPlayer') or r.get('fromPlayer')
                    if 'Land' in (r.get('types') or '') and 'Creature' not in (r.get('types') or ''): continue
                    games[r['game']]['res'].add((p,r['card']))
            elif r.get('rec')=='result': games[r['game']]['r']=r
        ag=dict(zip(meta['players'],meta['agents']))
        for g,G in games.items():
            if not G['r']: continue
            for p,a in ag.items():
                if a!='stock': continue
                dk=re.sub(r'^Ai\(\d+\)-','',p); won=G['r']['winner']==p
                games_per[dk]+=1; wins_per[dk]+=won
                for (pp,c) in G['res']:
                    if pp==p:
                        stats[(dk,c)]['n']+=1; stats[(dk,c)]['w']+=won
out=[]
for (dk,c),v in stats.items():
    n,w=v['n'],v['w']; N,W=games_per[dk],wins_per[dk]
    if n<12 or N-n<12: continue
    p1=w/n; p0=(W-w)/(N-n)
    out.append((dk,c,n,round(p1,2),round(p0,2),round(p1-p0,2), plans.get(dk,{}).get('search',{}).get('targets',{}).get(c,'-'), any(c in l['cards'] for l in plans.get(dk,{}).get('lines',[]))))
for dk in sorted({o[0] for o in out}):
    rows=sorted([o for o in out if o[0]==dk], key=lambda o:-o[5])
    print(f"== {dk} stock seats: {games_per[dk]} games, base win {wins_per[dk]/games_per[dk]:.2f}")
    for o in rows[:6]: print(f"   +{o[5]:.2f}  {o[1]:32s} n={o[2]:3d} P(win|resolved)={o[3]:.2f} vs {o[4]:.2f}  planTarget={o[6]} linePiece={o[7]}")
    tops=[o for o in rows if o[6]==8][:3]
    print('   plan value-8 cards, their lift:', [(o[1],o[5]) for o in sorted([o for o in out if o[0]==dk and o[6]==8], key=lambda o:-o[2])[:6]])
