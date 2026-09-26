"""Which plans list a commander in plan.tutors; do plan.tutors carry any restriction."""
import json, glob, os, collections
ROOT = r'C:/Users/Vatto/Magic Rules Engine'
files = sorted(glob.glob(ROOT + '/studies/**/plans_*.json', recursive=True))
print('plan files', len(files))
uniq = {}
keys = collections.Counter()
tutor_shape = collections.Counter()
for fp in files:
    d = json.load(open(fp, encoding='utf-8'))
    decks = d.get('decks', d)
    for name, p in decks.items():
        if not isinstance(p, dict):
            continue
        keys.update(p.keys())
        tut = p.get('tutors') or []
        for t in tut:
            tutor_shape[type(t).__name__] += 1
        cmd = p.get('commanders') or p.get('commander') or []
        if isinstance(cmd, str):
            cmd = [cmd]
        pod = os.path.basename(fp)
        key = (pod.replace('plans_', '').replace('.json', ''), name)
        tnames = [t if isinstance(t, str) else t.get('name') for t in tut]
        uniq.setdefault(key, (tuple(cmd), tuple(tnames), fp))
print('plan keys seen', dict(keys))
print('tutor entry types', dict(tutor_shape))
print('unique (pod, deck)', len(uniq))
hits = []
for (pod, name), (cmd, tnames, fp) in sorted(uniq.items()):
    inter = [c for c in cmd if c in tnames]
    if inter:
        hits.append((pod, name, inter))
print('decks with commander in tutors:', len(hits))
for h in hits:
    print('  ', h)
# commanders missing field?
nocmd = [k for k, v in uniq.items() if not v[0]]
print('plans without commanders field:', len(nocmd))
