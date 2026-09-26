import simload, glob, collections, sys
from lines import SETS
from simload import bare
EXILE=("Demonic Consultation","Tainted Pact")
for name in sys.argv[1:]:
    res=collections.Counter(); ex=[]
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            w=simload.win_info(G)
            hand=collections.defaultdict(collections.Counter); lib=collections.Counter()
            casts=collections.defaultdict(set)
            for r in G['stream']:
                if r.get('rec')!='zone': continue
                c=r['card']; fp=r.get('fromPlayer'); tp=r.get('toPlayer'); fz,tz=r['from'],r['to']; t=r['turn']
                if fz=='Hand' and fp: hand[fp][c]-=1
                if tz=='Hand' and tp: hand[tp][c]+=1
                if tz=='Stack' and fp: casts[(fp,t)].add(c)
                if c=="Thassa's Oracle" and tz=='Stack':
                    p=fp; agent=G['agents'].get(p,'?')
                    had=[x for x in EXILE if hand[p][x]>0]
                    pre=[x for x in EXILE if x in casts[(p,t)]]
                    won= w['winner']==p and w['method'].startswith('spell:Thassa')
                    k=(agent, 'exile spell cast first' if pre else ('exile spell IN HAND, not cast' if had else 'no exile spell available'), 'won' if won else 'no win')
                    res[k]+=1
                    ex.append((k,G['pod'],bare(p),simload.player_round(G,p,t)))
    print('==',name)
    for k,v in sorted(res.items()): print('  ',v,k)
    print('  examples',[e for e in ex if e[0][1]!='exile spell cast first'][:6])
