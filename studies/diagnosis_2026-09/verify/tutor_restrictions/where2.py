import json, glob, os, collections
S = os.path.dirname(os.path.abspath(__file__))
ROOT = r'C:/Users/Vatto/Magic Rules Engine'
src = open(os.path.join(S, 'classify.py'), encoding='utf-8').read().split("files = glob.glob")[0]
ns = {"__file__": os.path.join(S, "classify.py")}
exec(src, ns)
R, fact = ns['R'], ns['fact']
res = collections.Counter()
for fp in glob.glob(ROOT + '/studies/**/*.jsonl', recursive=True):
    txt = open(fp, encoding='utf-8').read()
    if '"tutor_cast"' not in txt:
        continue
    zones = collections.defaultdict(list)   # game -> [(turn, owner, card, to)]
    casts = []
    for line in txt.splitlines():
        if line.startswith('{"rec":"zone"'):
            r = json.loads(line)
            zones[r['game']].append((r['turn'], r.get('fromPlayer') or r.get('toPlayer'), r['card'], r['to']))
        elif '"tutor_cast"' in line:
            casts.append(json.loads(line))
    for c in casts:
        t, _, m = c['detail'].partition(' seeking ')
        z = 'Library(never moved)'
        for (tu, own, card, to) in zones[c['game']]:
            if tu >= c['turn']:
                break
            if card == m and own == c['player']:
                z = to
        legal = bool(R[t][0](fact(m)))
        res[('legal' if legal else 'ILLEGAL', z)] += 1
tot = collections.Counter()
for (k, z), v in sorted(res.items()):
    print(v, k, z); tot[z] += v
print(dict(tot))
