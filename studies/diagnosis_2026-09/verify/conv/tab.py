import json, collections, statistics
o = json.load(open('analyses.json'))
WIN = ('win the game', 'each opponent loses', 'infinite damage', 'infinite lifeloss', 'infinite life loss', 'infinite mill', 'infinite combat', 'lose the game')
def cls(c):
    p = ' | '.join(c.get('produces') or []).lower()
    if any(w in p for w in WIN): return 'win'
    return 'resource'
line_units = collections.Counter(); seat_units = {}
by_cls = collections.defaultdict(collections.Counter)
by_agent = collections.defaultdict(collections.Counter)
lags = collections.defaultdict(list)
fired = collections.Counter(); fired_causal = collections.Counter()
produces_seen = collections.Counter()
for x in o:
    games = {g['n']: g for g in x['games']}
    for name, d in x['decks'].items():
        ag = x['agents'].get(name, '?')
        for c in d['combos']:
            for p in c.get('produces') or []: produces_seen[p] += 1
            k = cls(c)
            spell_wins = 0
            for g in c['games']:
                if g['assembled_turn'] is None or not g['won']: continue
                G = games[g['n']]
                m = G['method']
                if m == 'spell': m = 'spell:' + G['detail']
                line_units[m] += 1
                by_cls[k][G['method']] += 1
                by_agent[ag][G['method']] += 1
                seat_units[(x['file'], g['n'], name)] = G['method']
                lags[k].append(G['ended_turn'] - g['assembled_turn'])
                if G['method'] == 'spell': spell_wins += 1
            if c['reading'] == 'fired':
                fired[k] += 1
                if spell_wins: fired_causal[k] += 1
tot = sum(line_units.values())
print('combo-game units assembled&won:', tot)
for m, v in line_units.most_common(): print('  ', v, m)
print('by class:')
for k, v in by_cls.items(): print('  ', k, sum(v.values()), dict(v))
print('by agent:')
for k, v in by_agent.items(): print('  ', k, sum(v.values()), dict(v))
sc = collections.Counter(seat_units.values())
print('distinct seat-games assembled&won:', len(seat_units), dict(sc))
for k, L in lags.items():
    L.sort()
    print('lag', k, 'n', len(L), 'median', statistics.median(L), 'same-turn(0)', sum(1 for l in L if l == 0), f'{sum(1 for l in L if l==0)/len(L):.0%}', '<=3', f'{sum(1 for l in L if l<=3)/len(L):.0%}')
print('fired readings (combo x file):', dict(fired), 'with >=1 spell-method conversion:', dict(fired_causal))
print('top produces:', produces_seen.most_common(25))
