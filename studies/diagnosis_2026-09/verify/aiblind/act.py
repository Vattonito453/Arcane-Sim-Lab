import json, glob, collections, sys, re
N2F = json.load(open('name2flags.json'))
def flagged(nm):
    f = N2F.get(nm) or (N2F.get(nm.split(' // ')[0]) if ' // ' in nm else None)
    return bool(f and 'All' in f)
R = r"C:/Users/Vatto/Magic Rules Engine/studies/"
for pat in sys.argv[1:]:
    act = collections.Counter(); onbf = collections.Counter(); castmsg = collections.Counter()
    percard = collections.defaultdict(collections.Counter)
    for fn in glob.glob(R+pat):
        meta=None; bf=set()
        for line in open(fn, encoding='utf-8'):
            if '"rec":"meta"' in line:
                meta=json.loads(line); pilot=dict(zip(meta['players'], meta.get('agents',['stock']*4))); continue
            if meta is None: break
            if '"STACK_ADD"' in line:
                r=json.loads(line); m=r['message']; nm=r.get('card') or ''
                if not flagged(nm): continue
                who = m.split(' ')[0]
                # player names contain spaces? players like Ai(1)-derevi; precon names may have spaces
                pl = next((pilot[p] for p in pilot if m.startswith(p+' ')), '?')
                if ' activated ' in m: act[pl]+=1; percard[nm][pl+':act']+=1
                elif ' cast ' in m: castmsg[pl]+=1
            elif '"rec":"zone"' in line and '"to":"Battlefield"' in line:
                r=json.loads(line)
                if r.get('token') or not flagged(r['card']) or 'Land' in (r.get('types') or ''): continue
                key=(r.get('game'), r.get('cardId'))
                if key in bf: continue
                bf.add(key); pl = pilot.get(r.get('toPlayer'),'?'); onbf[pl]+=1; percard[r['card']][pl+':bf']+=1
    print('==', pat, 'flagged nonland permanents entering bf', dict(onbf), '| activations of flagged cards', dict(act), '| cast msgs', dict(castmsg))
    rows = sorted(percard.items(), key=lambda kv: -(kv[1]['stock:bf']+kv[1]['plan:bf']))[:25]
    for nm,c in rows: print('   ', nm, dict(c))
