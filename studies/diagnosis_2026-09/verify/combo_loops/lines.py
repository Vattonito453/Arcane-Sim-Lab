import sys, glob, json, re, collections
sys.path.insert(0, 'engine')
import combos
decks = sorted(glob.glob('studies/human_ceiling/decks/*/dck/*.dck'))
print('decks', len(decks))
allv = []
per_deck = {}
missing = []
for p in decks:
    c = combos.combos_for_dck(p, fetch=False)
    if c is None:
        missing.append(p); continue
    inc = c.get('included', [])
    per_deck[p] = inc
    for v in inc:
        allv.append((p, v))
print('missing cache', missing)
print('total lines (seat-deck x variant)', len(allv))
print('unique variant ids', len({v['id'] for _, v in allv}))
act = [x for x in allv if re.search(r'\bactivat', x[1]['description'], re.I)]
print('description contains activat*', len(act))
tapcost = [x for x in allv if re.search(r'\bactivat|\{T\}|\btap\b', x[1]['description'], re.I)]
print('activat* or {T} or tap', len(tapcost))
gy = [x for x in allv if re.search(r'graveyard', x[1]['description'] + ' ' + x[1]['prerequisites'], re.I)]
print('mentions graveyard (desc+prereq)', len(gy))
# decks with Breach and Brain Freeze
bb = collections.Counter()
for p, inc in per_deck.items():
    for v in inc:
        if 'Underworld Breach' in v['cards'] and 'Brain Freeze' in v['cards']:
            bb[p] += 1
print('decks with Breach+BrainFreeze line', len(bb))
for p in bb: print('  ', p, bb[p])
json.dump([{'deck': p, **v} for p, v in allv], open(sys.argv[1], 'w'), indent=0)
