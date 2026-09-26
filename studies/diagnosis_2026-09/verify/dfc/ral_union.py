import json, glob, collections, re
for pod in ['CxKMqO36DdM','sZA0KqXCGrY']:
    deck = open(f'studies/human_ceiling/decks/{pod}/dck/joseph_ral.dck', encoding='utf-8').read()
    sec=None; names={}; 
    for line in deck.splitlines():
        m=re.match(r'\[(.*)\]',line)
        if m: sec=m.group(1); continue
        m=re.match(r'(\d+)\s+(.+?)(\|.*)?$',line.strip())
        if m and sec in('Main','Commander'): names[m.group(2)]=(sec,int(m.group(1)))
    total=sum(q for s,q in names.values()); dfc=[n for n in names if ' // ' in n]
    print(pod,'deck total',total,'main',sum(q for n,(s,q) in names.items() if s=='Main'),'dfc',dfc)
    union=set()
    for f in glob.glob(f'studies/**/*{pod}*.jsonl', recursive=True):
        for l in open(f,encoding='utf-8',errors='replace'):
            if '"rec":"zone"' not in l: continue
            r=json.loads(l)
            p=r.get('fromPlayer') if r.get('from') in ('Library','Hand','Command') else None
            if p and 'joseph_ral' in p and not r.get('token'): union.add(r['card'])
    main=set(n for n,(s,q) in names.items())
    fronts={n.split(' // ')[0]:n for n in dfc}
    print(' union seen from joseph_ral lib/hand/cmd:',len(union))
    print(' deck names never seen:',sorted(main-union))
    print(' seen not in deck:',sorted(union-main)[:20])
