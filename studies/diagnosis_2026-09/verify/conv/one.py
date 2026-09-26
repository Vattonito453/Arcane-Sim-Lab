import sys, json
from pathlib import Path
sys.path.insert(0, r'C:/Users/Vatto/Magic Rules Engine/engine')
import shim_log_adapter, analysis
f = sys.argv[1]
text = open(f, encoding='utf-8', errors='replace').read()
res = shim_log_adapter.parse_shim_jsonl(text, source=f)
res['file'] = Path(f).name
meta = res.setdefault('meta', {})
raw_meta = json.loads(text.split(chr(10),1)[0])
meta['decks'] = raw_meta['decks']
print('meta keys', list(meta.keys())[:20])
decks = meta.get('decks') or []
print(decks[:1])
pod_dir = Path(decks[0].replace(chr(92),'/')).parent
rep = analysis.analyse(res, deck_dirs=[pod_dir], fetch=False)
print(rep['summary'])
for i,g in enumerate(rep['games']): print(g)
for name,d in rep['decks'].items():
    for c in d['combos']:
        print(name, ' + '.join(c['cards']), 'asm', c['assembled_games'], '/', c['games_played'], 'conv', c['converted_games'], c['reading'])
        for g in c['games']:
            if g['assembled_turn'] is not None: print('    game', g['n'], 'asm_turn', g['assembled_turn'], 'won', g['won'])
