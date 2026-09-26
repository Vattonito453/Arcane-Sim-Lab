"""tutor_cast -> did the tutor go to the stack, did the sought piece leave the
library for this seat, was it then cast, and did its line assemble / win.
Agent and zone records are separate blocks per game, so join by turn."""
import json,glob,collections,os
S=r"C:/Users/Vatto/Magic Rules Engine/studies/"
pats=["agent_viability/runs_015_default/cell_*.jsonl","agent_viability/runs_winmax/cell_*.jsonl","agent_viability/runs_016_engine/cell_*.jsonl","behavior_rubric/runs_agent_shipping/*.jsonl","tutor_targeting/runs_stage2/*.jsonl"]
out=collections.Counter(); ex=collections.defaultdict(list)
for pat in pats:
    for f in glob.glob(S+pat):
        recs=[json.loads(l) for l in open(f,encoding='utf-8')]
        zones=collections.defaultdict(list); agents=collections.defaultdict(list); res={}
        for r in recs:
            if r.get('rec')=='zone': zones[r['game']].append(r)
            elif r.get('rec')=='agent': agents[r['game']].append(r)
            elif r.get('rec')=='result': res[r['game']]=r['winner']
        for g,ags in agents.items():
            for r in ags:
                if r['event']!='tutor_cast': continue
                p=r['player']; t=r['turn']; tutor,want=r['detail'].split(' seeking ',1)
                zs=[z for z in zones[g] if t<=(z.get('turn') or 0)<=t+4]
                cast=any(z['card']==tutor and z['to']=='Stack' and z.get('fromPlayer')==p for z in zs)
                got=any(z['card']==want and z['from']=='Library' and z.get('toPlayer')==p for z in zs)
                zall=[z for z in zones[g] if (z.get('turn') or 0)>=t]
                piece_played=any(z['card']==want and z['to'] in ('Stack','Battlefield') and (z.get('fromPlayer')==p or z.get('toPlayer')==p) for z in zall)
                k=('tutor cast' if cast else 'tutor NOT cast within 1 round', 'piece fetched' if got else 'piece not fetched', 'piece later played' if piece_played else 'piece never played', 'seat won' if res.get(g)==p else 'seat did not win')
                out[k]+=1
                if len(ex[k])<3: ex[k].append((os.path.basename(f),g,p,t,r['detail']))
tot=sum(out.values()); print('tutor_cast events:',tot)
for k,v in out.most_common(): print(f"{v:4d} {k}")
for k,v in list(ex.items())[:6]:
    print(k)
    for x in v: print('   ',x)
