import sys,glob,json,collections,os
sys.path.insert(0,r'C:/Users/Vatto/Magic Rules Engine/engine')
import combos
rows=[]
for d in sorted(glob.glob(r'C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks/*/dck/*.dck')):
    p=os.path.normpath(d).split(os.sep)
    pod=p[-3]; deck=p[-1][:-4]
    r=combos.combos_for_dck(d,fetch=False)
    for v in r['included']:
        rows.append(dict(pod=pod,deck=deck,**v))
json.dump(rows,open('all_lines.json','w'),indent=1)
print('rows',len(rows))
perdeck=set((r['pod'],r['deck'],tuple(sorted(r['cards']))) for r in rows)
print('per-deck unique',len(perdeck))
glob_u=set(tuple(sorted(r['cards'])) for r in rows)
print('global unique piece sets',len(glob_u))
ids=set(r['id'] for r in rows); print('unique spellbook ids',len(ids))
