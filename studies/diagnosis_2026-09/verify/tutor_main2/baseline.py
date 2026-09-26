import json,glob,re,sys,collections
from scripts import load,classify,params
S=load()
corpus=sys.argv[1]
files=sorted(glob.glob(corpus+'/*.jsonl'))
cnt=collections.defaultdict(collections.Counter)
apis=collections.defaultdict(collections.Counter)
for f in files:
    meta=None; active={}; recs=[]
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
        if r.get('rec')=='zone' and r['from']=='Hand' and r['to']=='Stack':
            pl=r['fromPlayer']; a=agent.get(pl)
            own=active.get((r['game'],r['turn']))==pl
            sc=S.get(r['card']); c=classify(sc) if sc else None
            t=r.get('types','')
            if c in ('hand','libtop'): k='TUTOR_'+c
            elif 'Sorcery' in t: k='sorcery'
            elif 'Instant' in t: k='instant'
            elif 'Creature' in t: k='creature'
            elif 'Land' in t: k='land'
            else: k='noncreature_perm'
            ph=r['phase'] if own else 'opp_'+r['phase']
            cnt[(a,k)][ph]+=1
            if k in ('sorcery',) and sc and sc['sp']:
                apis[(a,k)][params(sc['sp'][0]).get('SP')]+=1
for key in sorted(cnt):
    c=cnt[key]; tot=sum(c.values())
    m1=c['MAIN1']; m2=c['MAIN2']
    print(f"{key[0]:6s} {key[1]:18s} n={tot:4d} ownMAIN1={m1:4d} ({m1/tot*100:5.1f}%) ownMAIN2={m2:4d} ({m2/tot*100:5.1f}%) other={tot-m1-m2}")
print()
for k,v in apis.items(): print(k, v.most_common(12))
