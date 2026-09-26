import sys, json, os
from pathlib import Path
from multiprocessing import Pool
sys.path.insert(0, r'C:/Users/Vatto/Magic Rules Engine/engine')

def work(f):
    import shim_log_adapter, analysis
    try:
        text = open(f, encoding='utf-8', errors='replace').read()
        raw_meta = json.loads(text.split(chr(10), 1)[0])
        res = shim_log_adapter.parse_shim_jsonl(text, source=f)
        res['file'] = Path(f).name
        res.setdefault('meta', {})['decks'] = raw_meta['decks']
        pod_dir = Path(raw_meta['decks'][0].replace(chr(92), '/')).parent
        rep = analysis.analyse(res, deck_dirs=[pod_dir], fetch=False)
        agents = dict(zip([p.split('-',1)[1] if p.startswith('Ai(') else p for p in raw_meta['players']], raw_meta.get('agents') or ['?']*4))
        out = {'file': f, 'shim': raw_meta.get('shim'), 'agents': agents,
               'games': rep['games'], 'validity': rep.get('validity', {}).get('quality'),
               'decks': {}}
        for name, d in rep['decks'].items():
            out['decks'][name] = {'combo_status': d['combo_status'], 'combos': [
                {'cards': c['cards'], 'produces': c.get('produces'), 'reading': c['reading'],
                 'assembled_games': c['assembled_games'], 'converted_games': c['converted_games'],
                 'games': [{'n': g['n'], 'assembled_turn': g['assembled_turn'], 'won': g['won']} for g in c['games']]}
                for c in d['combos']]}
        return out
    except Exception as e:
        return {'file': f, 'error': repr(e)}

if __name__ == '__main__':
    files = json.load(open('files.json'))
    with Pool(4) as p:
        outs = p.map(work, files, chunksize=1)
    json.dump(outs, open('analyses.json', 'w'))
    print(len(outs), sum(1 for o in outs if 'error' in o))
    for o in outs:
        if 'error' in o: print(o['file'], o['error'])
