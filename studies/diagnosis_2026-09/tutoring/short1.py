"""Held short1 turns: a plan tutor sat in hand through the seat's own turn while the
best line was exactly one piece away (tutor_cast ELIGIBLE). Could the held tutor
even fetch the missing piece, and was it affordable (lands on battlefield >= cmc)?"""
import json, re, glob, collections, sys
from pathlib import Path
sys.path.insert(0,'.')
from parse2 import load_plans, POD_RE
from miss_reason import type_ok, fact
S=Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets={"av015":"agent_viability/runs_015_default","avwinmax":"agent_viability/runs_winmax","av016":"agent_viability/runs_016_engine"}
agg=collections.Counter()
for arm,dd in sets.items():
    for fn in sorted(glob.glob(str(S/dd/"cell_*.jsonl"))):
        plans=load_plans(str(S/dd/f"plans_{POD_RE.search(fn).group(1)}.json"))
        games=collections.defaultdict(lambda: {"z":[],"t":[],"r":None}); meta=None
        for line in open(fn,encoding='utf-8'):
            try: r=json.loads(line)
            except: continue
            if r.get('rec')=='meta': meta=r
            elif r.get('rec')=='zone': games[r['game']]['z'].append(r)
            elif r.get('rec')=='entry' and r['type']=='TURN': games[r['game']]['t'].append(r)
            elif r.get('rec')=='result': games[r['game']]['r']=r
        ag=dict(zip(meta['players'],meta['agents']))
        p=[x for x,a in ag.items() if a=='plan'][0]
        plan=plans.get(re.sub(r'^Ai\(\d+\)-','',p),{})
        lines=[set(l['cards']) for l in plan.get('lines',[])]; tut=set(plan.get('tutors',[]))
        for g,G in games.items():
            if not G['r']: continue
            whose={int(re.match(r"Turn (\d+)",e['message']).group(1)): re.match(r"Turn \d+ \((.+)\)",e['message']).group(1) for e in G['t']}
            zone={}; zi=0; Z=G['z']
            for t in range(1,max(whose)+1 if whose else 1):
                while zi<len(Z) and (Z[zi].get('turn') or 0)<=t:
                    z=Z[zi]; zone[z['cardId']]=(z['to'], z.get('toPlayer') or z.get('fromPlayer'), z['card'], z.get('types') or ''); zi+=1
                if whose.get(t)!=p: continue
                H={nm for (zn,c,nm,ty) in zone.values() if zn=='Hand' and c==p}
                B={nm for (zn,c,nm,ty) in zone.values() if zn=='Battlefield' and c==p}
                C={nm for (zn,c,nm,ty) in zone.values() if zn=='Command' and c==p}
                lands=sum(1 for (zn,c,nm,ty) in zone.values() if zn=='Battlefield' and c==p and 'Land' in ty)
                held=H & tut
                if not held: continue
                cand=[L for L in lines if not L<=B]
                if not cand: continue
                best=min(len(L-B-H-C) for L in cand)
                if best==0: continue
                if best!=1: continue
                missing={next(iter(L-B-H-C)) for L in cand if len(L-B-H-C)==1}
                can=any(type_ok(tu,m) for tu in held for m in missing)
                afford=any(lands >= (fact(tu).get('cmc') or 0) for tu in held)
                agg[('can fetch a missing piece' if can else 'NO held tutor can fetch any missing piece', 'affordable by lands' if afford else 'not affordable by lands alone')]+=1
tot=sum(agg.values())
for k,v in agg.most_common(): print(f"{v:4d} ({100*v/tot:.0f}%) {k}")
