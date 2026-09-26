import json, collections
o = json.load(open('analyses.json'))
cnt = collections.Counter()
for x in o:
    need = []
    for name, d in x['decks'].items():
        for c in d['combos']:
            if "Thassa's Oracle" in c['cards']:
                for g in c['games']:
                    if g['assembled_turn'] is not None:
                        need.append((name, g['n'], g['won'], ' + '.join(c['cards'])))
    if not need: continue
    outc = collections.defaultdict(list)
    for l in open(x['file'], encoding='utf-8', errors='replace'):
        if '"GAME_OUTCOME"' not in l: continue
        r = json.loads(l); outc[r['game']].append(r['message'])
    for name, n, won, line in need:
        msgs = [m for m in outc[n - 1] if ('-' + name + ' ') in m]
        tag = 'won' if won else ('selfdeck' if any('empty library' in m for m in msgs) else 'lost/other')
        cnt[(line, tag)] += 1
for k, v in sorted(cnt.items()): print(v, k)
