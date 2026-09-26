import json,sys,glob,collections
for pat in sys.argv[1:]:
    c=collections.Counter(); t=collections.Counter(); ev=collections.Counter(); metas=set()
    files=sorted(glob.glob(pat))
    for f in files:
        for line in open(f,encoding='utf-8'):
            try: r=json.loads(line)
            except: continue
            c[r.get('rec')]+=1
            if r.get('rec')=='entry': t[r.get('type')]+=1
            if r.get('rec')=='agent': ev[r.get('event')]+=1
            if r.get('rec')=='meta': metas.add((r.get('shim'),tuple(r.get('agents',[]))))
    print(pat,len(files)); print(' recs',dict(c)); print(' entry types',dict(t)); print(' agent events',dict(ev)); print(' metas',list(metas)[:5])
