import json, collections, statistics
o = json.load(open('analyses.json')); L = json.load(open('lethal.json'))
WIN = ('win the game', 'each opponent loses', 'infinite damage', 'infinite lifeloss', 'infinite life loss', 'infinite mill', 'infinite combat', 'lose the game')
agg = collections.defaultdict(lambda: collections.Counter())
lagd = collections.defaultdict(list)
plan_lag = collections.defaultdict(list)
for x in o:
    lg = L[x['file']]
    for name, d in x['decks'].items():
        ag = x['agents'].get(name)
        for c in d['combos']:
            p = ' | '.join(c.get('produces') or []).lower()
            k = 'win' if any(w in p for w in WIN) else 'resource'
            for g in c['games']:
                if g['assembled_turn'] is None or not g['won']: continue
                G = x['games'][g['n'] - 1]
                m = G['method']
                if m == 'combat damage / life loss':
                    deaths = [dd for dd in (lg.get(str(g['n'] - 1)) or []) if not dd[1].endswith('-' + name)]
                    m = max(deaths)[2] if deaths else 'unknown'
                lag = G['ended_turn'] - g['assembled_turn']
                if ag == 'plan': plan_lag[k].append(lag)
                if k == 'win':
                    key = ' + '.join(c['cards'])[:70]
                    agg[key][m] += 1
                    lagd[key].append(lag)
for key, v in sorted(agg.items(), key=lambda kv: -sum(kv[1].values())):
    print(sum(v.values()), dict(v), 'lag med', statistics.median(lagd[key]), 'same', sum(1 for l in lagd[key] if l == 0), '|', key)
for k, Lg in plan_lag.items():
    print('PLAN lag', k, len(Lg), 'median', statistics.median(Lg), f'same-turn {sum(1 for l in Lg if l==0)/len(Lg):.0%}')
