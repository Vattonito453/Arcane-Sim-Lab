import json, glob, collections
R = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
N2F = json.load(open('name2flags.json'))
fl = lambda n: 'All' in (N2F.get(n) or [])
for arm in ('runs_015_default','runs_016_engine','runs_winmax'):
    res = collections.Counter()
    for fn in glob.glob(R+arm+'/cell_*.jsonl'):
        names = collections.defaultdict(set); acts = []
        for line in open(fn, encoding='utf-8'):
            if '"rec":"zone"' in line or '"STACK_ADD"' in line or '"STACK_RESOLVE"' in line:
                r = json.loads(line)
                key = (r.get('game'), r.get('cardId'))
                if r['rec']=='zone': names[key].add(r['card'])
                elif r.get('type')=='STACK_ADD':
                    if ' activated ' in r['message'] and fl(r.get('card','')): acts.append((key, r['card']))
                    if ' cast ' in r['message']: names[key].add('CAST:'+r['card'])
        for key, nm in acts:
            other = {n for n in names[key] if n != nm and n != 'CAST:'+nm}
            res[(nm, 'copy/other-name' if other else 'original')] += 1
            if other: res[('via', tuple(sorted(other)))] += 1
    print(arm, dict(res))
