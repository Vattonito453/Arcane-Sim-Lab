import json, re, collections
from multiprocessing import Pool
LIFE = re.compile(r'^Life: (.+?) (-?\d+) > (-?\d+)')
DMG = re.compile(r' deals (\d+) (combat |non-combat )?damage to (Ai\(\d+\)-[^.]+)\.')
def work(f):
    ents = collections.defaultdict(list)
    for l in open(f, encoding='utf-8', errors='replace'):
        try: r = json.loads(l)
        except Exception: continue
        if r.get('rec') == 'entry' and r.get('type') in ('DAMAGE', 'LIFE'):
            ents[r['game']].append((r['seq'], r['type'], r['message']))
    out = {}
    for g, E in ents.items():
        E.sort()
        last = {}
        deaths = []
        for seq, t, m in E:
            if t == 'DAMAGE':
                for mm in DMG.finditer(m):
                    last[mm.group(3)] = (seq, 'combat' if mm.group(2) == 'combat ' else 'noncombat')
            else:
                mm = LIFE.match(m)
                if mm and int(mm.group(2)) > 0 and int(mm.group(3)) <= 0:
                    p = mm.group(1)
                    d = last.get(p)
                    kind = d[1] if d and seq - d[0] <= 6 else 'lifeloss'
                    deaths.append((seq, p, kind))
        out[g] = deaths
    return f, out
if __name__ == '__main__':
    files = json.load(open('files.json'))
    with Pool(4) as p:
        res = dict(p.map(work, files, chunksize=1))
    json.dump(res, open('lethal.json', 'w'))
    print(len(res))
