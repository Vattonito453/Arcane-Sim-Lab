import json,glob,re,sys,collections
from scripts import load,classify
S=load()
corpus=sys.argv[1]
files=sorted(glob.glob(corpus+'/*.jsonl'))
cnt=collections.Counter()   # (agent, cls, phase, ownturn)
names=collections.Counter()
handsize_rows=[]
for f in files:
    meta=None; active={}; hand=collections.defaultdict(set)
    recs=[]
    for line in open(f,encoding='utf-8'):
        try: r=json.loads(line)
        except: continue
        if r.get('rec')=='meta': meta=r; continue
        recs.append(r)
    if not meta: continue
    agent={p:a for p,a in zip(meta['players'],meta['agents'])}
    for r in recs:
        if r.get('rec')=='entry' and r.get('type')=='TURN':
            m=re.match(r'Turn (\d+) \((.*)\)',r['message'])
            if m: active[(r['game'],int(m.group(1)))]=m.group(2)
    for r in recs:
        if r.get('rec')!='zone': continue
        if r['from']=='Hand' and r['to']=='Stack':
            sc=S.get(r['card'])
            c=classify(sc) if sc else None
            if c in ('hand','libtop'):
                pl=r['fromPlayer']; a=agent.get(pl,'?')
                act=active.get((r['game'],r['turn']))
                own = 'own' if act==pl else ('opp' if act else '?')
                cnt[(a,c,r['phase'],own)]+=1
                names[(a,c,r['card'])]+=1
def summarize(a,c):
    tot=sum(v for k,v in cnt.items() if k[0]==a and k[1]==c)
    m2=sum(v for k,v in cnt.items() if k[0]==a and k[1]==c and k[2]=='MAIN2')
    byph=collections.Counter()
    for k,v in cnt.items():
        if k[0]==a and k[1]==c: byph[(k[2],k[3])]+=v
    print(f"{a:6s} {c:7s} total={tot} MAIN2={m2} ({(m2/tot*100 if tot else 0):.1f}%) ", dict(byph))
for a in ['stock','plan']:
    for c in ['hand','libtop']:
        summarize(a,c)
print()
for k,v in sorted(names.items()): print(k,v)
