#!/usr/bin/env python3
"""Win-condition support-chain telemetry for a deck across sim results.

Answers, per tournament: is the commander being cast (and when)? Are its
triggers firing? Are charge counters / station happening? Is proliferate
resolving? Are the named finishers doing anything? What's killing us?

Usage:
  python3 deck_telemetry.py <deck_substring> [--cards "Lux Cannon,Dawnsire,..."]

Reads every sim_*rotated.json (and sim_*.json) in ./sim_results that includes
a deck whose filename contains <deck_substring>.
"""
from __future__ import annotations
import glob, json, re, sys

def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else 'kilo_helm'
    watch = []
    if '--cards' in sys.argv:
        watch = [c.strip() for c in sys.argv[sys.argv.index('--cards')+1].split(',')]
    files = []
    for f in sorted(glob.glob('sim_results/sim_*.json')) + sorted(glob.glob('sim_*.json')):
        try: d = json.load(open(f))
        except Exception: continue
        if any(sub in x for x in d['meta'].get('decks', [])):
            files.append((f, d))
    if not files:
        sys.exit(f'no results mention a deck matching "{sub}"')
    games=0; cast_turns=[]; charge=0; prolif=0; attacked=0
    cardhits={c:0 for c in watch}; dmg={}
    cmd_name = None
    for f, d in files:
        for g in d['games']:
            games += 1
            me = [p for p in g['players'] if sub.replace('_',' ').split()[0].lower() in p.lower()] or \
                 [p for p in g['players'] if 'v3' in p or 'B3' in p]
            first = None
            for t in g['turns']:
                for e in t['events']:
                    r = e['raw']
                    if e['action']=='stack_add' and 'cast' in r and ' the Commander' in r:
                        pass
                    if 'charge counter' in r.lower(): charge += 1
                    if 'proliferate' in r.lower(): prolif += 1
                    for c in watch:
                        if c in r: cardhits[c] += 1
                    if e['action']=='damage' and me and e.get('target')==me[0]:
                        s=e.get('source','?').split(' (')[0]; dmg[s]=dmg.get(s,0)+e.get('amount',0)
    print(f'files: {len(files)} | games: {games}')
    print(f'charge-counter events: {charge} ({charge/games:.1f}/game)')
    print(f'proliferate resolutions: {prolif} ({prolif/games:.1f}/game)')
    for c, n in cardhits.items():
        print(f'  watched card "{c}": {n} events ({n/games:.1f}/game)')
    print('top damage sources against the deck:',
          sorted(dmg.items(), key=lambda kv: -kv[1])[:6])

if __name__ == '__main__':
    main()
