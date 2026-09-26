"""Duplicate tutor_cast logs (castTries allows 2 per tutor per turn) and
no-search breakdown by how the tutor searches."""
import json, glob, os, re, collections, sys
S = os.path.dirname(os.path.abspath(__file__))
sys.argv = ['x']
ROOT = r'C:/Users/Vatto/Magic Rules Engine'
src = open(os.path.join(S, 'classify.py'), encoding='utf-8').read()
src = src.split("files = glob.glob")[0]
ns = {"__file__": os.path.join(S, "classify.py")}
exec(src, ns)
R, fact = ns['R'], ns['fact']
files = glob.glob(ROOT + '/studies/**/*.jsonl', recursive=True)
keys = collections.Counter()
seen_keys = set()
uniq_rows = []
for fp in files:
    with open(fp, encoding='utf-8') as fh:
        for line in fh:
            if '"tutor_cast"' not in line:
                continue
            r = json.loads(line)
            k = (fp, r['game'], r['turn'], r['player'], r['detail'])
            keys[k] += 1
            if k not in seen_keys:
                seen_keys.add(k)
                uniq_rows.append(r)
print('events', sum(keys.values()), 'distinct (file,game,turn,player,detail)', len(keys),
      'dupe extra', sum(v - 1 for v in keys.values()))
c = collections.Counter()
for r in uniq_rows:
    t, _, m = r['detail'].partition(' seeking ')
    pred, how, cond = R[t]
    c['ILLEGAL' if not pred(fact(m)) else 'legal'] += 1
print('dedup classes', dict(c), f"{c['ILLEGAL']/sum(c.values()):.1%}")
# how breakdown overall
h = collections.Counter()
for k, v in keys.items():
    t = k[4].partition(' seeking ')[0]
    h[R[t][1]] += v
print('events by how', dict(h))
