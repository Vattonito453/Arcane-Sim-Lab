import json, glob, collections, sys
N2F = json.load(open('name2flags.json'))
fl = lambda n: 'All' in (N2F.get(n) or (N2F.get(n.split(' // ')[0]) if ' // ' in n else None) or [])
R = r"C:/Users/Vatto/Magic Rules Engine/studies/"
for pat in sys.argv[1:]:
    c = collections.Counter(); ex = {}
    for fn in glob.glob(R+pat):
        meta=None; last = {}
        for line in open(fn, encoding='utf-8'):
            if meta is None:
                if '"rec":"meta"' in line: meta=json.loads(line); pilot=dict(zip(meta['players'], meta['agents']))
                continue
            if '"rec":"agent"' in line:
                r=json.loads(line); last[r['player']] = (r['game'], r['turn'], r['event'], r['detail'][:60])
            elif '"rec":"zone"' in line and '"from":"Hand","to":"Stack"' in line:
                r=json.loads(line)
                if not fl(r['card']): continue
                p = r.get('fromPlayer'); 
                if pilot.get(p)!='plan': continue
                l = last.get(p)
                ev = l[2] if l and l[0]==r['game'] and l[1]==r.get('turn') and r['card'].split(' //')[0] in l[3] else 'none-matching'
                c[ev]+=1; ex.setdefault(ev, (r['card'], l))
    print(pat, dict(c)); 
    for k,v in ex.items(): print('   ', k, v)
