"""Tutor hold times with mulligans handled: a tutor 'instance' starts when the
card enters its owner's hand (turn>=1, or still in hand when turn 1 starts) and
ends at the first exit from hand. Outcome = cast (Hand->Stack) / discarded /
exiled / to library / still in hand at game end."""
import json, re, glob, collections, sys
from pathlib import Path
sys.path.insert(0,'.')
from parse2 import TUTORS, TUTOR_MODE
S=Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets={"av015":"agent_viability/runs_015_default/cell_*.jsonl","avwinmax":"agent_viability/runs_winmax/cell_*.jsonl","av016":"agent_viability/runs_016_engine/cell_*.jsonl","rubric_ship":"behavior_rubric/runs_agent_shipping/*.jsonl","tt_stock":"tutor_targeting/runs_stock/shim_raw_*.jsonl","tt_stage2":"tutor_targeting/runs_stage2/shim_raw_*.jsonl"}
for arm,gl in sets.items():
    res=collections.defaultdict(collections.Counter); held=collections.defaultdict(list); openc=collections.defaultdict(list)
    for fn in sorted(glob.glob(str(S/gl))):
        meta=None; games=collections.defaultdict(list); results={}
        for line in open(fn,encoding='utf-8'):
            try: r=json.loads(line)
            except: continue
            if r.get('rec')=='meta': meta=r
            elif r.get('rec')=='zone': games[r['game']].append(r)
            elif r.get('rec')=='result': results[r['game']]=r
        ag=dict(zip(meta['players'],meta['agents'])); n=len(meta['players'])
        for g,Z in games.items():
            if g not in results: continue
            inhand={}  # cid -> (enter_turn, player, name)
            for z in Z:
                t=z.get('turn') or 0
                if z['to']=='Hand' and z['card'] in TUTORS and TUTOR_MODE.get(z['card'])=='spell':
                    inhand[z['cardId']]=(t,z['toPlayer'],z['card'])
                elif z['from']=='Hand' and z['cardId'] in inhand:
                    t0,p,nm=inhand.pop(z['cardId'])
                    if t==0: continue  # mulligan
                    out='cast' if z['to']=='Stack' else ('discarded' if z['to']=='Graveyard' else z['to'])
                    a=ag.get(p); res[a][out]+=1
                    r0=(max(t0,1)-1)//n+1; r1=(t-1)//n+1
                    if out=='cast':
                        held[a].append(r1-r0)
                        if t0==0: openc[a].append(r1)
            for cid,(t0,p,nm) in inhand.items():
                res[ag.get(p)]['still in hand at end']+=1
    print('==',arm)
    for a in res:
        tot=sum(res[a].values()); c=res[a]['cast']
        hs=sorted(held[a]); oc=sorted(openc[a])
        print(f"  {a:5s} tutor-SPELL instances={tot} cast={100*c/tot:.0f}% still-in-hand-at-end={100*res[a]['still in hand at end']/tot:.0f}% discarded={100*res[a]['discarded']/tot:.0f}%  held rounds: median={hs[len(hs)//2] if hs else '-'} p75={hs[3*len(hs)//4] if hs else '-'} held>=2 rounds={100*sum(1 for h in hs if h>=2)/max(1,len(hs)):.0f}% | opening-hand tutors cast: n={len(oc)} median round={oc[len(oc)//2] if oc else '-'} in R1-2={100*sum(1 for x in oc if x<=2)/max(1,len(oc)):.0f}%")
