import json, sys, collections, math
from pathlib import Path
BASE=Path(r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability")
arms=sys.argv[1:]
W=collections.defaultdict(list)
for arm in arms:
    for f in sorted((BASE/arm).glob('cell_*.jsonl')):
        meta=None
        for line in open(f,encoding='utf-8'):
            if '"rec":"meta"' in line[:20]: meta=json.loads(line); continue
            if '"rec":"result"' not in line[:20]: continue
            r=json.loads(line)
            w=r.get('winner')
            if not w: continue
            ag=dict(zip(meta['players'],meta['agents']))[w]
            deck=w.split(')-',1)[1]
            W[(deck,ag)].append(r['turns'])
def show(label,keys):
    t=[x for k in keys for x in W[k]]
    if not t: print(label,'none'); return
    print(f"{label:30s} n={len(t):3d} mean turn {sum(t)/len(t):.1f}  mean round(turn/4) {sum(t)/len(t)/4:.2f}  mean ceil(turn/4) {sum(math.ceil(x/4) for x in t)/len(t):.2f}")
decks=sorted({k[0] for k in W})
for d in decks:
    show(d+' plan',[(d,'plan')]); show(d+' stock',[(d,'stock')])
O=['rograkh_silas','tymna_thrasios']
show('ORACLE plan',[(d,'plan') for d in O]); show('ORACLE stock',[(d,'stock') for d in O])
show('ALL plan',[(d,'plan') for d in decks]); show('ALL stock',[(d,'stock') for d in decks])
show('nonOracle stock',[(d,'stock') for d in decks if d not in O])
