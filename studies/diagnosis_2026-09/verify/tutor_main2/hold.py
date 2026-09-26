import json,glob,re,sys,collections,statistics
from scripts import load,classify
S=load()
files=sorted(glob.glob(sys.argv[1]+'/cell_*.jsonl'))
held=collections.defaultdict(list); castround=collections.defaultdict(list); frac=collections.defaultdict(list)
never=collections.Counter(); drawn=collections.Counter()
for f in files:
    meta=None; recs=[]
    for line in open(f,encoding='utf-8'):
        try: r=json.loads(line)
        except: continue
        if r.get('rec')=='meta': meta=r; continue
        recs.append(r)
    agent={p:a for p,a in zip(meta['players'],meta['agents'])}
    turns=collections.defaultdict(list)  # game -> [(turn, active)]
    gl={}
    for r in recs:
        if r.get('rec')=='entry' and r.get('type')=='TURN':
            m=re.match(r'Turn (\d+) \((.*)\)',r['message'])
            if m: turns[r['game']].append((int(m.group(1)),m.group(2)))
        if r.get('rec')=='result': gl[r['game']]=r['turns']
    def ownturns(g,pl,t0,t1):
        return sum(1 for t,a in turns[g] if a==pl and t0<t<=t1)
    def roundof(g,t):
        # round = number of turns taken by first player up to t
        first=turns[g][0][1] if turns[g] else None
        return sum(1 for tt,a in turns[g] if a==first and tt<=t)
    inhand={}
    for r in recs:
        if r.get('rec')!='zone': continue
        g=r['game']
        sc=S.get(r['card']); c=classify(sc) if sc else None
        if c not in ('hand','libtop'): continue
        if r['to']=='Hand' and r['turn']>=0:
            inhand[(g,r['cardId'])]=(r['turn'],r['toPlayer'])
        if r['from']=='Hand' and r['to']=='Stack' and (g,r['cardId']) in inhand:
            t0,pl=inhand.pop((g,r['cardId']))
            a=agent[pl]
            held[(a,c)].append(ownturns(g,pl,t0,r['turn']))
            castround[(a,c)].append(roundof(g,r['turn']))
            if gl.get(g): frac[(a,c)].append(r['turn']/gl[g])
        elif r['from']=='Hand' and (g,r['cardId']) in inhand:
            inhand.pop((g,r['cardId']))
    for (g,cid),(t0,pl) in inhand.items():
        # still in hand at game end (never cast)
        pass
for k in sorted(held):
    h=held[k]
    print(k,'n=',len(h),'own-turns held: mean %.2f median %s  share held>=1 own turn: %.1f%%'%(statistics.mean(h),statistics.median(h),100*sum(1 for x in h if x>=1)/len(h)),
          ' cast round mean %.1f'%statistics.mean(castround[k]), ' frac of game %.2f'%statistics.mean(frac[k]))
