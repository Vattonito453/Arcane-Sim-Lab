"""Join each tutor_cast to the search Forge actually resolved (search_seen with
src=<tutor>), same file/game/player, at or after the cast turn. Forge's
fetchList is the ground truth of what was legal to find."""
import json, glob, os, re, collections, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = r'C:/Users/Vatto/Magic Rules Engine'
import importlib.util
spec = importlib.util.spec_from_file_location('cl', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'classify_lib.py'))

files = glob.glob(ROOT + '/studies/**/*.jsonl', recursive=True)
out = collections.Counter()
examples = collections.defaultdict(list)
per_pred = collections.Counter()
PRED = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'illegal_pairs.json')))
ill = {(t, m) for t, m, v in PRED['illegal']}
for fp in files:
    recs = []
    with open(fp, encoding='utf-8') as fh:
        for line in fh:
            if '"agent"' not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('rec') != 'agent':
                continue
            if r.get('event') in ('tutor_cast', 'search_seen'):
                recs.append(r)
    has_seen = any(r['event'] == 'search_seen' for r in recs)
    for i, r in enumerate(recs):
        if r['event'] != 'tutor_cast':
            continue
        t, _, m = r['detail'].partition(' seeking ')
        pred_illegal = (t, m) in ill
        if not has_seen:
            out[('no_search_seen_in_file', pred_illegal)] += 1
            continue
        match = None
        for r2 in recs[i + 1:]:
            if r2['event'] != 'search_seen' or r2.get('game') != r.get('game') or r2.get('player') != r.get('player'):
                continue
            src = re.search(r' src=(.*)$', r2['detail'])
            if src and src.group(1) == t:
                if r2['turn'] - r['turn'] <= 1:
                    match = r2
                break
        if match is None:
            out[('no_search_resolved', pred_illegal)] += 1
            examples[('no_search_resolved', pred_illegal)].append((os.path.relpath(fp, ROOT), r['game'], r['turn'], r['detail']))
            continue
        d = match['detail']
        cp = re.search(r'comboPick=(\S+)', d).group(1)
        miss = re.search(r' missing=(.*?) picked=', d).group(1)
        picked = re.search(r' picked=(.*?) planPick=', d).group(1)
        k = ('offered' if cp == 'yes' else 'NOT_offered', pred_illegal)
        out[k] += 1
        examples[k].append((os.path.relpath(fp, ROOT), r['game'], r['turn'], r['detail'], 'missing=' + miss, 'picked=' + picked))
for k, v in sorted(out.items(), key=str):
    print(v, k)
for k in examples:
    print('==', k)
    for e in examples[k][:6]:
        print('   ', e)
