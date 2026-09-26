"""Independent recount: for every nonland, non-token card that reached a hand
(excluding cards returned to library during turn-0 mulligans), did its owner
ever cast it (Hand->Stack) or put it (Hand->Battlefield)? Split by Forge
RemoveDeck:All flag and by pilot (plan/stock)."""
import json, glob, sys, collections
N2F = json.load(open('name2flags.json'))
def flag(nm):
    f = N2F.get(nm)
    if f is None and ' // ' in nm: f = N2F.get(nm.split(' // ')[0])
    if f is None: return 'unk'
    return 'All' if 'All' in f else 'ok'
REPO = r"C:/Users/Vatto/Magic Rules Engine/studies/"
def run(pattern, label):
    tot = collections.Counter(); percard = collections.defaultdict(collections.Counter)
    seatgames = collections.Counter()
    files = sorted(glob.glob(REPO + pattern))
    for fn in files:
        meta = None; games = collections.defaultdict(list)
        with open(fn, encoding='utf-8') as fh:
            for line in fh:
                if '"rec":"zone"' not in line and '"rec":"meta"' not in line and '"rec":"result"' not in line: continue
                r = json.loads(line)
                if r['rec'] == 'meta': meta = r; continue
                games[r.get('game')].append(r)
        if meta is None: continue
        pilot = dict(zip(meta['players'], meta.get('agents', ['stock']*4)))
        for g, recs in games.items():
            if not any(r['rec']=='result' for r in recs): continue  # unfinished game
            for p in meta['players']: seatgames[pilot[p]] += 1
            st = {}  # cid -> [owner, name, inhand, outcome]
            for r in recs:
                if r['rec'] != 'zone': continue
                ty = r.get('types') or ''
                if 'Land' in ty.split() or r.get('token'): continue
                cid = r.get('cardId'); fr, to = r.get('from'), r.get('to')
                if to == 'Hand':
                    s = st.get(cid)
                    if s is None: st[cid] = [r.get('toPlayer'), r['card'], True, None]
                    else: s[2] = True
                elif fr == 'Hand' and cid in st and st[cid][2]:
                    s = st[cid]; s[2] = False
                    if to == 'Library' and (r.get('turn') or 0) == 0:
                        if s[3] is None: s[3] = 'mull'
                        continue
                    if to == 'Stack': s[3] = 'cast' if s[3] in (None,'mull','other') else s[3]
                    elif to == 'Battlefield': s[3] = s[3] if s[3]=='cast' else 'put'
                    else:
                        if s[3] in (None,'mull'): s[3] = 'other'
            for cid,(own,nm,inhand,out) in st.items():
                if out == 'mull' and not inhand: continue  # mulliganed away, never held again
                if out == 'mull': out = None
                pl = pilot.get(own, '?'); fl = flag(nm)
                o = out or 'held'
                tot[(pl,fl,'n')] += 1; tot[(pl,fl,o)] += 1
                if fl == 'All': percard[nm][(pl,'n')] += 1; percard[nm][(pl,o)] += 1
    print(f'== {label}: {len(files)} files, seat-games {dict(seatgames)}')
    for pl in sorted({k[0] for k in tot}):
        for fl in ('ok','All','unk'):
            n = tot[(pl,fl,'n')]
            if not n: continue
            print(f'  {pl:5s} {fl:4s} n={n:6d} ' + ' '.join(f'{o}={tot[(pl,fl,o)]/n:.3f}' for o in ('cast','put','held','other'))
                  + (f'  per-seat-game={n/seatgames[pl]:.2f}' if fl=='All' else ''))
    return tot, percard
if __name__ == '__main__':
    out = {}
    for pat,label in [(a.split('=')[0], a.split('=')[1]) for a in sys.argv[1:]]:
        tot, pc = run(pat, label)
        out[label] = {nm: {f'{k[0]}:{k[1]}': v for k, v in c.items()} for nm, c in pc.items()}
    json.dump(out, open('percard_' + '_'.join(out.keys()) + '.json','w'), indent=0)
