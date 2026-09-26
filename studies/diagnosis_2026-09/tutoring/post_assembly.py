"""At each plan-seat search, was some plan line ALREADY fully on the seat's
battlefield (lineOfSight skips it as 'assembled, done here')? Such searches
keep feeding more line pieces into a board that already 'has' a combo."""
import json, re, glob, collections, sys
from pathlib import Path
sys.path.insert(0,'.')
from parse2 import load_plans, POD_RE
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
S=Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets={"av015":"agent_viability/runs_015_default","avwinmax":"agent_viability/runs_winmax","av016":"agent_viability/runs_016_engine"}
agg=collections.Counter(); won=collections.Counter()
for arm,dd in sets.items():
    for fn in sorted(glob.glob(str(S/dd/"cell_*.jsonl"))):
        plans=load_plans(str(S/dd/f"plans_{POD_RE.search(fn).group(1)}.json"))
        games=collections.defaultdict(lambda: {"z":[],"a":[],"r":None}); meta=None
        for line in open(fn,encoding='utf-8'):
            try: r=json.loads(line)
            except: continue
            if r.get('rec')=='meta': meta=r
            elif r.get('rec')=='zone': games[r['game']]['z'].append(r)
            elif r.get('rec')=='agent': games[r['game']]['a'].append(r)
            elif r.get('rec')=='result': games[r['game']]['r']=r
        ag=dict(zip(meta['players'],meta['agents']))
        for g,G in games.items():
            if not G['r']: continue
            p=[x for x,a in ag.items() if a=='plan'][0]
            plan=plans.get(re.sub(r'^Ai\(\d+\)-','',p),{})
            lines=plan.get('lines',[])
            seen=[a for a in G['a'] if a['event']=='search_seen' and a['player']==p]
            if not seen: continue
            first_asm=None; first_win_asm=None
            board=collections.Counter(); zone={}
            zi=0; Z=G['z']
            for s in seen:
                while zi<len(Z) and (Z[zi].get('turn') or 0) < s['turn']:
                    z=Z[zi]; zone[z['cardId']]=(z['to'], z.get('toPlayer') or z.get('fromPlayer'), z['card']); zi+=1
                B={nm for (zn,ctl,nm) in zone.values() if zn=='Battlefield' and ctl==p}
                asm=[l for l in lines if set(l['cards'])<=B]
                wasm=[l for l in asm if WIN.search(' ; '.join(l.get('produces',[])))]
                key=('post-assembly (a line fully on board)' if asm else 'pre-assembly')
                agg[key]+=1
                if asm and not wasm: agg['  of which only NON-WIN lines assembled']+=1
                if asm: won[key]+= G['r']['winner']==p
tot=agg['pre-assembly']+agg['post-assembly (a line fully on board)']
for k,v in agg.items(): print(f"{k:45s} {v:4d} ({100*v/tot:.0f}%)")
print('seat won in games w/ post-assembly searches (by search):', won)
