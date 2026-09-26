import json, collections
from pathlib import Path
HERE=Path('.')
reps=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((HERE/'reports').glob('*.json'))]
rows=collections.OrderedDict()
for r in reps:
    gm={g['n']:g for g in r['games']}
    for deck,d in r['decks'].items():
        for c in d['combos']:
            k=(r['_set'],deck," + ".join(c['cards']))
            row=rows.setdefault(k,{'produces':c['produces'],'games':[]})
            for g in c['games']:
                row['games'].append(dict(g,ended=gm[g['n']]['ended_turn'],method=gm[g['n']]['method'],file=r['file']))
for k,v in rows.items():
    if any(s in k[2] for s in ("Helm of the Host","Staff of Domination","Cephalid Illusionist")):
        a=[g for g in v['games'] if g['assembled_turn'] is not None]
        cv=[g for g in a if g['won']]
        if cv or 'Helm' in k[2]:
            print(k, 'played',len(v['games']),'assembled',len(a),'conv',len(cv),[g['ended']-g['assembled_turn'] for g in cv], v['produces'][:4])
