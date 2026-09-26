"""Where was the sought piece when tutor_cast fired? (file order = event order)"""
import json, glob, os, collections
S = os.path.dirname(os.path.abspath(__file__))
ROOT = r'C:/Users/Vatto/Magic Rules Engine'
src = open(os.path.join(S, 'classify.py'), encoding='utf-8').read().split("files = glob.glob")[0]
ns = {"__file__": os.path.join(S, "classify.py")}
exec(src, ns)
R, fact = ns['R'], ns['fact']
files = glob.glob(ROOT + '/studies/**/*.jsonl', recursive=True)
res = collections.Counter()
for fp in files:
    with open(fp, encoding='utf-8') as fh:
        txt = fh.read()
    if '"tutor_cast"' not in txt:
        continue
    loc = {}
    game = None
    for line in txt.splitlines():
        if not line.startswith('{"rec":"zone"') and '"tutor_cast"' not in line:
            continue
        r = json.loads(line)
        if r.get('game') != game:
            game = r.get('game'); loc = {}
        if r['rec'] == 'zone':
            owner = r.get('toPlayer') or r.get('fromPlayer')
            loc[(owner, r['card'])] = r['to']
        elif r.get('event') == 'tutor_cast':
            t, _, m = r['detail'].partition(' seeking ')
            z = loc.get((r['player'], m), 'Library(never moved)')
            legal = bool(R[t][0](fact(m)))
            res[('legal' if legal else 'ILLEGAL', z)] += 1
tot = collections.Counter()
for (k, z), v in sorted(res.items()):
    print(v, k, z)
    tot[z] += v
print(dict(tot))
