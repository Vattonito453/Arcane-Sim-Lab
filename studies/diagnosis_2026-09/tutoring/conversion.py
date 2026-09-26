import json, re, collections, sys
from pathlib import Path
sys.argv=['x']
from fetch_cats import cat, load_plans, ROOT
HERE=Path('.')
BASE={"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax","av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping/plans"}
POD=re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
pc={}
def plan_for(arm,s):
    p=ROOT/'studies'/BASE[arm]/f"plans_{POD.search(s['file']).group(1)}.json"
    if p not in pc: pc[p]=load_plans(p)
    return pc[p].get(s['deck'],{})
agg=collections.defaultdict(lambda: collections.Counter())
games_fetch=collections.Counter()
over_portal=collections.Counter()
for arm in BASE:
    d=json.load(open(f'v2_{arm}.json'))
    G={(g['file'],g['game']):g for g in d['games']}
    per_seat=collections.defaultdict(set)
    for s in d['searches']:
        if s.get('agent')!='plan': continue
        tk=s.get('taken')
        if not tk or tk=='-': continue
        c=cat(tk,plan_for(arm,s))
        g=G[(s['file'],s['game'])]
        won = g['winner']==s['player']
        soon = won and g['win_round'] is not None and g['win_round']-s['round']<=2
        agg[c]['n']+=1; agg[c]['won']+=won; agg[c]['won_within2']+=soon
        per_seat[(s['file'],s['game'],s['player'])].add(c)
        st=s.get('steer')
        if st and st['over']=='Portal to Phyrexia':
            over_portal[(st['mode'],st['steer'])]+=1
    # per-game: seat fetched a win-line piece?
    for g in d['games']:
        for p,a in g['agents'].items():
            if a!='plan': continue
            cats=per_seat.get((g['file'],g['game'],p),set())
            k='fetched win-line piece' if 'win-line piece' in cats else ('fetched only other' if cats else 'no search')
            games_fetch[(k,'n')]+=1; games_fetch[(k,'won')]+= g['winner']==p
print('plan-seat searches by category (pooled av015+winmax+016+rubric_ship):')
for c,v in sorted(agg.items(), key=lambda kv:-kv[1]['n']):
    print(f"  {c:40s} n={v['n']:4d} seat won game={100*v['won']/v['n']:.0f}%  won within 2 rounds of the fetch={100*v['won_within2']/v['n']:.0f}%")
print('plan-seat games:')
for k in ('fetched win-line piece','fetched only other','no search'):
    n=games_fetch[(k,'n')]; w=games_fetch[(k,'won')]
    if n: print(f"  {k:28s} games={n:4d} won={w} ({100*w/n:.0f}%)")
print('steers that overrode a stock Portal to Phyrexia pick:', sum(over_portal.values()), over_portal.most_common(8))
