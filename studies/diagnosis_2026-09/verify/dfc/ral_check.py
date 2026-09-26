import json, glob, collections, re, sys
files = [f for f in glob.glob('studies/**/*.jsonl', recursive=True) if 'joseph_ral' in open(f, encoding='utf-8', errors='replace').read(3000)]
DFC = ['Ral, Monsoon Mage','Ral, Leyline','Birgi','Harnfel','Sea Gate','Shatterskull','Sink into Stupor','Soporific','Pinnacle Monk','Mystic Peak']
tot = collections.Counter()
for f in sorted(files):
    games = 0; cmd_exit = collections.Counter(); dfc_hits = collections.Counter(); zone_n = 0
    ral_player=None; seen_names=collections.defaultdict(set); shim=None; wins=collections.Counter()
    for l in open(f, encoding='utf-8', errors='replace'):
        try: r = json.loads(l)
        except: continue
        k = r.get('rec')
        if k == 'meta':
            shim = r.get('shim')
            ral_player = [p for p in r['players'] if 'joseph_ral' in p]
        elif k == 'result':
            games += 1; wins[r.get('winner')] += 1
        elif k == 'zone':
            zone_n += 1
            if r.get('from') == 'Command':
                cmd_exit[(r.get('fromPlayer'), r.get('card'))] += 1
            seen_names[r.get('fromPlayer') or r.get('toPlayer')].add(r.get('card'))
        s = l
        for d in DFC:
            if d in s: dfc_hits[d] += 1
    rp = ral_player[0] if ral_player else None
    ral_cmd = sum(v for (p,c),v in cmd_exit.items() if p == rp)
    others_cmd = sorted(set((p.split('-',1)[1],c) for (p,c) in cmd_exit if p != rp))
    tot['files'] += 1; tot['games'] += games; tot['ral_cmd'] += ral_cmd; tot['ral_wins'] += wins.get(rp,0)
    for d,v in dfc_hits.items(): tot['hit:'+d] += v
    print(f.split('studies/')[-1], 'shim', shim, 'games', games, 'zone', zone_n, 'ral_cmd_exits', ral_cmd, 'ral_wins', wins.get(rp,0), 'ral_distinct_cards', len(seen_names.get(rp,())), 'dfc_hits', dict(dfc_hits), 'other_cmd', others_cmd[:6])
print(dict(tot))
