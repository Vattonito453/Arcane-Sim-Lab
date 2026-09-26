import json,glob,re,sys,collections
from scripts import load,classify
S=load()
PRE=('UPKEEP','DRAW','MAIN1','COMBAT_BEGIN','COMBAT_DECLARE_ATTACKERS','COMBAT_DECLARE_BLOCKERS','COMBAT_DAMAGE','COMBAT_END')
res=collections.Counter()
for f in sorted(glob.glob(sys.argv[1]+'/cell_*.jsonl')):
    meta=None; recs=[]
    for line in open(f,encoding='utf-8'):
        try: r=json.loads(line)
        except: continue
        if r.get('rec')=='meta': meta=r; continue
        recs.append(r)
    agent={p:a for p,a in zip(meta['players'],meta['agents'])}
    active={}; nxt={}
    tl=collections.defaultdict(list)
    for r in recs:
        if r.get('rec')=='entry' and r.get('type')=='TURN':
            m=re.match(r'Turn (\d+) \((.*)\)',r['message'])
            if m: active[(r['game'],int(m.group(1)))]=m.group(2); tl[r['game']].append((int(m.group(1)),m.group(2)))
    zs=[r for r in recs if r.get('rec')=='zone']
    for i,r in enumerate(zs):
        if not(r['from']=='Hand' and r['to']=='Stack'): continue
        sc=S.get(r['card']); c=classify(sc) if sc else None
        if c not in ('hand','libtop'): continue
        g=r['game']; pl=r['fromPlayer']; a=agent[pl]; own=active.get((g,r['turn']))==pl
        when='pre' if (own and r['phase'] in PRE) else ('ownM2' if own else 'opp')
        if c=='hand':
            fetched=None
            for r2 in zs[i+1:i+80]:
                if r2['game']!=g or r2['turn']!=r['turn']: break
                if r2['from']=='Library' and r2['to']=='Hand' and r2['toPlayer']==pl: fetched=r2; break
            used='nofetch'
            if fetched:
                used='unused'
                for r3 in zs[i+1:]:
                    if r3['game']!=g or r3['turn']!=r['turn']: break
                    if r3['cardId']==fetched['cardId'] and r3['from']=='Hand':
                        used='cast_same_turn' if r3['to'] in ('Stack','Battlefield') else 'lost_'+r3['to']; break
            res[(a,c,when,used)]+=1
        else:
            # fetched card: Library->Library for pl right after; when is it drawn (turn) and next cast?
            fetched=None
            for r2 in zs[i+1:i+80]:
                if r2['game']!=g: break
                if r2['from']=='Library' and r2['to']=='Library' and (r2.get('toPlayer')==pl or r2.get('fromPlayer')==pl): fetched=r2; break
            if not fetched: res[(a,c,when,'nofetch')]+=1; continue
            drawn=None
            for r3 in zs[i+1:]:
                if r3['game']!=g: break
                if r3['cardId']==fetched['cardId'] and r3['from']=='Library' and r3['to']!='Library': drawn=r3; break
            if not drawn: res[(a,c,when,'never_drawn')]+=1; continue
            same = drawn['turn']==r['turn']
            res[(a,c,when,'drawn_same_turn' if same else 'drawn_later')]+=1
for k in sorted(res): print(res[k],k)
