import simload,glob,collections,re,sys
from lines import SETS, game_lines
from tutor import GENERIC, ENGINE
from simload import bare
RES=re.compile(r"^(.+?) \((\d+)\) - Counter (.+?) \((\d+)\)")
ADD=re.compile(r"^(Ai\(\d\)-\S+) (cast|activated|triggered) (.+?)(?: targeting .*)?$", re.S)
for name in sys.argv[1:]:
    cls=collections.defaultdict(collections.Counter); prot=collections.Counter(); tot=collections.Counter()
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            lines=game_lines(G)
            owner={}; cardname={}
            for e in G['entries']:
                if e['type']=='STACK_ADD':
                    m=ADD.match(e['message'])
                    if m and e.get('cardId') is not None and m.group(2)=='cast':
                        owner[e['cardId']]=m.group(1); cardname[e['cardId']]=m.group(3)
                if e['type']=='STACK_RESOLVE':
                    m=RES.match(e['message'])
                    if not m: continue
                    cid=int(m.group(2)); tid=int(m.group(4)); tname=m.group(3)
                    P=owner.get(cid); Q=owner.get(tid)
                    if not P or not Q or P==Q: continue
                    ag=G['agents'].get(P,'?')
                    pl=simload.plans(G['pod']).get(bare(Q),{})
                    roles=pl.get('roles',{})
                    if tname in simload.commanders(G['pod'],bare(Q)): c='commander'
                    elif any(tname in L for L in lines[Q]): c='combo piece'
                    elif tname in GENERIC or tname in set(pl.get('tutors',[])): c='tutor'
                    elif tname in ENGINE: c='engine/draw'
                    elif roles.get(tname)=='enabler': c='ramp'
                    elif roles.get(tname) in('protection','removal'): c='interaction (counter war)'
                    else: c='other'
                    cls[ag][c]+=1; tot[ag]+=1
                    # protective: target is a counter aimed at P's spell
                    # (resolve messages for the target not yet seen; approximate: target role protection)
    print('==',name)
    for ag,c in cls.items():
        n=tot[ag]; print('  %s: resolved counters %d:'%(ag,n), {k:'%d (%.0f%%)'%(v,100*v/n) for k,v in c.most_common()})
