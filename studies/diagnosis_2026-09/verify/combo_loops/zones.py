import json, glob, collections, sys
S='/c/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad/diagnosis/'
S='C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad/diagnosis/'
lines=json.load(open(S+'verify/combo_loops/lines.json'))
full={}
for f in glob.glob(S+'combo_data/raw/*.json'):
    d=json.load(open(f))
    for k in ('included','almostIncluded'):
        for v in (d.get('results') or {}).get(k) or []:
            full[v['id']]=v
print('full variants known', len(full))
miss=[l['id'] for l in lines if l['id'] not in full]
print('cached line ids missing from raw', len(miss), len(set(miss)))
zc=collections.Counter(); nonbf=[]; examples=collections.Counter()
reqzones=collections.Counter()
for l in lines:
    v=full.get(l['id'])
    if not v: continue
    zs=set(); nb=[]
    for u in v['uses']:
        z=u.get('zoneLocations') or []
        zs|=set(z)
        if not set(z) & {'B','H','C'}:  # cannot be satisfied by battlefield/hand/command
            nb.append((u['card']['name'], ''.join(z)))
    for r in v.get('requires') or []:
        reqzones[''.join(r.get('zoneLocations') or [])]+=1
    if nb:
        nonbf.append((l['deck'], l['id'], nb))
        for n in nb: examples[n]+=1
print('lines with a piece whose zoneLocations excludes B/H/C:', len(nonbf), 'unique variants', len({x[1] for x in nonbf}))
print(examples.most_common(20))
# Alternative: any piece allowing G/E/L at all
anyg=0
for l in lines:
    v=full.get(l['id'])
    if v and any(set(u.get('zoneLocations') or []) & {'G','E','L'} for u in v['uses']): anyg+=1
print('lines where some piece lists G/E/L among its zones', anyg)
print('requires (templates) zone combos', reqzones.most_common(10))
# Show zoneLocations distribution
zd=collections.Counter()
for l in lines:
    v=full.get(l['id'])
    if not v: continue
    for u in v['uses']: zd[''.join(u.get('zoneLocations') or [])]+=1
print('piece zone distribution', zd.most_common())
