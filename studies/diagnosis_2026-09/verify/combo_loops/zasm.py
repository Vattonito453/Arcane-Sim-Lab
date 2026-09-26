"""Zone-aware assembly for cEDH plan lines: every piece in one of ITS Spellbook zoneLocations
(B battlefield, H hand, G graveyard, E exile, L library, C command) at the same moment."""
import json, glob, collections, os, sys
from pathlib import Path
S='C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad/diagnosis/'
lines=json.load(open(S+'verify/combo_loops/lines.json'))
full={}
for f in glob.glob(S+'combo_data/raw/*.json'):
    d=json.load(open(f))
    for k in ('included','almostIncluded'):
        for v in (d.get('results') or {}).get(k) or []: full[v['id']]=v
ZMAP={'Battlefield':'B','Hand':'H','Graveyard':'G','Exile':'E','Library':'L','Command':'C'}
deck_lines=collections.defaultdict(list)
for l in lines:
    key=Path(l['deck'].replace(chr(92),'/'))
    tag=key.parts[-3]+'/'+key.stem
    v=full[l['id']]
    req={}
    for u in v['uses']:
        req[u['card']['name']]=set(u.get('zoneLocations') or ['B'])
    nonB=any(not (z & {'B','H','C'}) for z in req.values())
    deck_lines[tag].append({'id':l['id'],'req':req,'nonB':nonB,'cards':list(req)})
def fits(name, zone_counts, zset):
    return any(zone_counts.get((name,z),0)>0 for z in zset)
files=glob.glob('studies/**/*.jsonl', recursive=True)
stats=collections.Counter()
per_line=collections.Counter()
gy_cast=collections.Counter(); bf_enter=collections.Counter()
for f in files:
    fh=open(f,encoding='utf-8',errors='replace')
    try: meta=json.loads(fh.readline())
    except: fh.close(); continue
    if meta.get('rec')!='meta' or not meta.get('decks'): fh.close(); continue
    seat={}
    for p,d,a in zip(meta['players'],meta['decks'],meta.get('agents') or ['stock']*4):
        pp=Path(d.replace(chr(92),'/'))
        if 'human_ceiling' in d:
            tag=pp.parts[-3]+'/'+pp.stem
            if tag in deck_lines: seat[p]=(tag,a)
    if not seat: fh.close(); continue
    zone_of={}  # (g,cardId)->(owner,name,zone)
    counts=collections.defaultdict(collections.Counter)  # (g,player)->Counter((name,zone))
    asm={}; games=set()
    for line in fh:
        if '"rec":"zone"' not in line and '"rec":"result"' not in line: continue
        r=json.loads(line); g=r.get('game')
        if r['rec']=='result': games.add(g); continue
        name=r.get('card'); cid=r.get('cardId')
        fz=ZMAP.get(r.get('from')); tz=ZMAP.get(r.get('to'))
        fp=r.get('fromPlayer'); tp=r.get('toPlayer')
        if r.get('to')=='Stack' and r.get('from')=='Graveyard': gy_cast[(name, seat.get(tp,('',''))[1] if tp in seat else 'other')]+=1
        if r.get('to')=='Battlefield' and name in ('Underworld Breach','Isochron Scepter','Clock of Omens','Kiki-Jiki, Mirror Breaker','Emiel the Blessed'):
            bf_enter[name]+=1
        k=(g,cid)
        if k in zone_of:
            o,n,z=zone_of[k]
            if z: counts[(g,o)][(n,z)]-=1
        else:
            # first sighting: it came from 'from' zone; we did not count it there
            pass
        owner=tp or fp
        zone_of[k]=(owner,name,tz)
        if tz: counts[(g,owner)][(name,tz)]+=1
        if owner in seat:
            tag=seat[owner][0]
            c=counts[(g,owner)]
            for i,ln in enumerate(deck_lines[tag]):
                if (g,owner,i) in asm: continue
                ok=True
                for n,zs in ln['req'].items():
                    zs2=set(zs)
                    if 'L' in zs2: 
                        # library: assume present unless seen leaving and not returned; approximate as ok
                        continue
                    if 'C' in zs2 and not any(c.get((n,z),0)>0 for z in zs2): 
                        # commander never leaves Command without a record; treat unseen as in Command
                        if not any((n,z) in c for z in ZMAP.values()):
                            continue
                    if not any(c.get((n,z),0)>0 for z in zs2): ok=False; break
                if ok: asm[(g,owner,i)]=r.get('turn')
    fh.close()
    for g in games:
        for p,(tag,a) in seat.items():
            for i,ln in enumerate(deck_lines[tag]):
                kind='nonB' if ln['nonB'] else 'BHC'
                stats[(a,kind,'seat_line_games')]+=1
                if (g,p,i) in asm:
                    stats[(a,kind,'assembled')]+=1
                    per_line[(a,tag,' + '.join(f"{n}:{''.join(sorted(z))}" for n,z in ln['req'].items()))]+=1
for k in sorted(stats): print(k, stats[k])
print('\nnonB lines assembled (zone-aware):')
for k,v in per_line.most_common():
    if any((':G' in part or ':E' in part or ':L' in part) and not any(x in part.split(':')[1] for x in 'BHC') for part in k[2].split(' + ')):
        print(' ',v,k)
print('\ngraveyard->stack casts (name, seatkind):', gy_cast.most_common(30))
print('enter battlefield:', bf_enter)
