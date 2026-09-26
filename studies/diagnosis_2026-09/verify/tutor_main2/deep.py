import json,glob,re,sys,collections
from scripts import load,classify
S=load()
files=sorted(glob.glob(sys.argv[1]+'/cell_*.jsonl'))
out=collections.Counter(); hs=collections.defaultdict(collections.Counter)
cause=collections.Counter(); sameturn=collections.Counter()
examples=[]
for f in files:
    meta=None; recs=[]
    for line in open(f,encoding='utf-8'):
        try: r=json.loads(line)
        except: continue
        if r.get('rec')=='meta': meta=r; continue
        recs.append(r)
    agent={p:a for p,a in zip(meta['players'],meta['agents'])}
    active={}
    for r in recs:
        if r.get('rec')=='entry' and r.get('type')=='TURN':
            m=re.match(r'Turn (\d+) \((.*)\)',r['message'])
            if m: active[(r['game'],int(m.group(1)))]=m.group(2)
    # agent events keyed by game,turn,player
    ag=collections.defaultdict(list)
    for r in recs:
        if r.get('rec')=='agent': ag[(r['game'],r['turn'],r['player'])].append((r['event'],r['detail']))
    zs=[r for r in recs if r.get('rec')=='zone']
    hand=collections.defaultdict(set)
    for i,r in enumerate(zs):
        g=r['game']
        if r['from']=='Hand' and r['to']=='Stack':
            sc=S.get(r['card']); c=classify(sc) if sc else None
            if c in ('hand','libtop'):
                pl=r['fromPlayer']; a=agent[pl]
                own=active.get((g,r['turn']))==pl
                ph=r['phase']; pre = own and ph in ('UPKEEP','DRAW','MAIN1','COMBAT_BEGIN','COMBAT_DECLARE_ATTACKERS','COMBAT_DECLARE_BLOCKERS','COMBAT_DAMAGE','COMBAT_END')
                n=len(hand[(g,pl)])
                hs[(a,c,'preMAIN2' if pre else ('own_'+ph if own else 'opp_'+ph))][n]+=1
                if a=='plan' and pre:
                    evs=[e for e in ag[(g,r['turn'],pl)] if r['card'] in e[1]]
                    kinds=sorted(set(e[0] for e in evs))
                    cause[(c,tuple(kinds))]+=1
                if a=='stock' and c=='hand':
                    # fetched card: next Library->Hand for pl in same game/turn
                    fetched=None
                    for r2 in zs[i+1:i+60]:
                        if r2['game']!=g or r2['turn']!=r['turn']: break
                        if r2['from']=='Library' and r2['to']=='Hand' and r2['toPlayer']==pl:
                            fetched=r2; break
                    used=False
                    if fetched:
                        for r3 in zs[i+1:]:
                            if r3['game']!=g or r3['turn']!=r['turn']: break
                            if r3['cardId']==fetched['cardId'] and r3['from']=='Hand':
                                used=r3['to']; break
                    sameturn[(ph if own else 'opp_'+ph, 'fetched' if fetched else 'nofetch', used or 'unused')]+=1
        if r['to']=='Hand': hand[(g,r['toPlayer'])].add(r['cardId'])
        if r['from']=='Hand': hand[(g,r['fromPlayer'])].discard(r['cardId'])
print('HAND SIZE AT CAST (includes the tutor):')
for k in sorted(hs): print(' ',k, dict(sorted(hs[k].items())))
print('\nPLAN pre-MAIN2 tutor casts: agent events naming the card same turn:')
for k,v in cause.most_common(): print(' ',v,k)
print('\nSTOCK hand-tutor: was the fetched card cast/played the same turn?')
for k,v in sorted(sameturn.items()): print(' ',v,k)
