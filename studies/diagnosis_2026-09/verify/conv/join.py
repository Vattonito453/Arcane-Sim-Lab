import json, collections
o = json.load(open('analyses.json')); L = json.load(open('lethal.json'))
WIN = ('win the game', 'each opponent loses', 'infinite damage', 'infinite lifeloss', 'infinite life loss', 'infinite mill', 'infinite combat', 'lose the game')
def cls(c):
    p = ' | '.join(c.get('produces') or []).lower()
    return 'win' if any(w in p for w in WIN) else 'resource'
mismatch = 0
res = collections.defaultdict(collections.Counter)
seat = {}
for x in o:
    lg = L[x['file']]
    keys = sorted(int(k) for k in lg)
    if len(x['games']) != len(keys) and len(keys) > 0: mismatch += 1
    for name, d in x['decks'].items():
        for c in d['combos']:
            for g in c['games']:
                if g['assembled_turn'] is None or not g['won']: continue
                G = x['games'][g['n'] - 1]
                m = G['method']
                if m == 'combat damage / life loss':
                    deaths = lg.get(str(g['n'] - 1)) or []
                    # last death that is not the winner
                    deaths = [dd for dd in deaths if not dd[1].endswith('-' + name)]
                    m = 'life0:' + (max(deaths)[2] if deaths else 'unknown')
                res[cls(c)][m] += 1
                seat[(x['file'], g['n'], name)] = m
print('files with game-count mismatch', mismatch)
for k, v in res.items(): print(k, sum(v.values()), dict(v))
tot = collections.Counter()
for v in res.values(): tot.update(v)
print('all', sum(tot.values()), dict(tot))
print('seat-games', len(seat), dict(collections.Counter(seat.values())))
