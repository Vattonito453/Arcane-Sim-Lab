import json,glob,re,sys,collections
from scripts import load,classify,params
S=load()
files=[]
for c in sys.argv[1:]: files+=sorted(glob.glob(c+'/cell_*.jsonl'))+sorted(glob.glob(c+'/*shim*.jsonl'))
files=sorted(set(files))
cnt=collections.defaultdict(collections.Counter); names=collections.defaultdict(collections.Counter)
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
            sc=S.get(r['card']); 
            if not sc or not sc['sp']: continue
            p=params(sc['sp'][0])
            if p.get('SP')!='ChangeZone': continue
            org=p.get('Origin','?'); dst=p.get('Destination','?')
            t=r.get('types','')
            spd='instant' if 'Instant' in t else ('sorcery' if 'Sorcery' in t else 'other')
            key=(a,org+'->'+dst,spd)
            ph=r['phase'] if own else 'opp_'+r['phase']
            cnt[key][ph]+=1; names[key][r['card']]+=1
for key in sorted(cnt, key=lambda k:(k[0],k[1],k[2])):
    c=cnt[key]; tot=sum(c.values())
    pre=sum(v for ph,v in c.items() if ph in ('UPKEEP','DRAW','MAIN1','COMBAT_BEGIN','COMBAT_DECLARE_ATTACKERS'))
    print(f"{key[0]:6s} {key[1]:28s} {key[2]:8s} n={tot:4d} own-preMAIN2={pre:4d} ownMAIN2={c['MAIN2']:4d} {dict(c.most_common(5))}")
    print('        ', dict(names[key].most_common(6)))
