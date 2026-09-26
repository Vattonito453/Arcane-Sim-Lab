"""Independent re-count: seats that assemble a full plan line, and whether/when they win.
Tracks zones by cardId (not name), uses zone 'turn' (= global turn, verified against LAND entries)."""
import json, re, glob, os, sys, collections, statistics
ROOT = "C:/Users/Vatto/Magic Rules Engine"
SETS = {
    'agent093': 'studies/behavior_rubric/runs_agent_093/*.jsonl',
    'stock_hc': 'studies/human_ceiling/runs/*.jsonl',
    'agentship': 'studies/behavior_rubric/runs_agent_shipping/*.jsonl',
    'av015': 'studies/agent_viability/runs_015_default/*.jsonl',
    'av016': 'studies/agent_viability/runs_016_engine/*.jsonl',
    'winmax': 'studies/agent_viability/runs_winmax/*.jsonl',
}
PODS = ["2iA_Jt0d6sM","5A6o18Bra0Y","B421mac67IE","Bq-nFi0f1jA","CxKMqO36DdM","OuY6mdiXbHU","n7WpsqsZtdQ","sZA0KqXCGrY"]
AI = re.compile(r"^Ai\(\d+\)-")
def bare(p): return AI.sub("", p or "")
def pod_of(path):
    b = os.path.basename(path)
    for p in PODS:
        if p in b: return p
    return None
_pl = {}
def plan_lines(pod, deck):
    if pod not in _pl:
        f = f"{ROOT}/studies/behavior_rubric/plans_{pod}.json"
        _pl[pod] = json.load(open(f, encoding='utf-8'))['decks'] if os.path.exists(f) else {}
    out = []; seen = set()
    for l in _pl[pod].get(deck, {}).get('lines', []):
        k = tuple(sorted(l['cards']))
        if k not in seen:
            seen.add(k); out.append((k, tuple(l.get('produces', []))))
    return out

def games(path):
    meta = None; G = collections.OrderedDict()
    for line in open(path, encoding='utf-8'):
        try: r = json.loads(line)
        except Exception: continue
        if r.get('rec') == 'meta': meta = r; continue
        g = r.get('game')
        if g is None: continue
        d = G.setdefault(g, {'entries': [], 'zones': [], 'agent': [], 'result': None})
        rec = r.get('rec')
        if rec == 'entry': d['entries'].append(r)
        elif rec == 'zone': d['zones'].append(r)
        elif rec == 'agent': d['agent'].append(r)
        elif rec == 'result': d['result'] = r
    for g, d in G.items():
        if d['result'] is None: continue
        d['meta'] = meta; d['file'] = path; d['g'] = g
        yield d

TURN = re.compile(r"^Turn (\d+) \((.+)\)$")
def method(d):
    ents = d['entries']; w = d['result'].get('winner')
    for e in ents:
        if e.get('type') == 'GAME_OUTCOME' and ('by spell' in e['message'] or 'due to effect' in e['message']):
            m = re.search(r"'([^']+)'", e['message'])
            return 'spell:' + m.group(1)
        if e.get('type') == 'GAME_OUTCOME' and 'empty library' in e['message']:
            deck_out = True
    if not w: return 'none'
    kinds = collections.Counter()
    life = re.compile(r"Life: (.+) (-?\d+) > (-?\d+)")
    for i, e in enumerate(ents):
        if e.get('type') != 'LIFE': continue
        m = life.match(e['message'])
        if not m: continue
        who, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        if b <= 0 < a:
            k = 'lifeloss'
            for j in range(i - 1, max(0, i - 60), -1):
                if ents[j].get('type') == 'DAMAGE' and ents[j]['message'].rstrip('.').endswith(who):
                    k = 'combat' if ' combat damage' in ents[j]['message'] else 'noncombat'; break
            kinds[k] += 1
    if any('empty library' in e['message'] for e in ents if e.get('type') == 'GAME_OUTCOME'):
        kinds['deckout'] += 1
    return max(kinds, key=kinds.get) if kinds else 'other'

def analyse(d):
    meta = d['meta']; players = meta['players']; agents = dict(zip(players, meta['agents']))
    pod = pod_of(d['file'])
    tp = {}; owncount = collections.Counter(); ownr = {}
    for e in d['entries']:
        if e.get('type') == 'TURN':
            m = TURN.match(e['message'])
            if m:
                t = int(m.group(1)); p = m.group(2); owncount[p] += 1; tp[t] = p; ownr[t] = owncount[p]
    last = max(tp) if tp else 0
    def pround(p, t):  # own turns p has started by global turn t
        return sum(1 for tt, pp in tp.items() if pp == p and tt <= t)
    lines = {p: plan_lines(pod, bare(p)) for p in players}
    types = {}
    bf = collections.defaultdict(dict); hand = collections.defaultdict(dict)
    stack_cast = collections.defaultdict(set)  # (p,turn) -> names moved to stack by p
    first = {}; asm_turns = collections.defaultdict(set)
    zs = sorted(d['zones'], key=lambda r: r['turn'])  # stable: keeps order within a turn
    for r in zs:
        c = r['card']; cid = r['cardId']; t = r['turn']
        if r.get('types'): types.setdefault(c, r['types'])
        fp, tpl = r.get('fromPlayer'), r.get('toPlayer')
        if r['from'] == 'Battlefield' and fp: bf[fp].pop(cid, None)
        if r['from'] == 'Hand' and fp: hand[fp].pop(cid, None)
        if r['to'] == 'Battlefield' and tpl: bf[tpl][cid] = c
        if r['to'] == 'Hand' and tpl: hand[tpl][cid] = c
        if r['to'] == 'Stack' and fp: stack_cast[(fp, t)].add(c)
        for p in {fp, tpl}:
            if p not in lines: continue
            bfn = set(bf[p].values()); hn = set(hand[p].values())
            for L, prod in lines[p]:
                ok = True
                for x in L:
                    ty = types.get(x, '')
                    spell = ('Instant' in ty or 'Sorcery' in ty)
                    if x in bfn: continue
                    if spell and (x in hn or x in stack_cast[(p, t)]): continue
                    ok = False; break
                if ok:
                    asm_turns[(p, L)].add(t)
                    if (p, L) not in first: first[(p, L)] = (t, prod)
    res = d['result']; w = res.get('winner')
    meth = method(d)
    rows = []
    for p in players:
        mine = [(t, L, prod) for (q, L), (t, prod) in first.items() if q == p]
        if not lines[p]: continue
        row = dict(file=os.path.basename(d['file']), g=d['g'], pod=pod, deck=bare(p), agent=agents.get(p),
                   nlines=len(lines[p]), won=(w == p), winner=w, method=meth if w == p else None,
                   last=last, win_round=owncount.get(w) if w else None, timedOut=res.get('timedOut'), turnCapped=res.get('turnCapped'))
        if mine:
            t0 = min(m[0] for m in mine)
            row['asm_turn'] = t0
            row['asm_round'] = pround(p, t0)
            row['asm_lines'] = [(' + '.join(L), list(prod)) for (t, L, prod) in mine if t == t0]
            row['all_lines'] = [' + '.join(L) for (t, L, prod) in mine]
            row['lines_first'] = [(' + '.join(L), list(prod), t, pround(p, t), ownr.get(t,0)) for (t, L, prod) in mine]
            row['same_turn_win'] = (w == p and last == t0)
            row['table_round_asm'] = ownr.get(t0, 0)
            row['table_round_end'] = ownr.get(last, 0)
            row['lag_rounds'] = ownr.get(last, 0) - ownr.get(t0, 0)
            row['own_round_end'] = owncount.get(p)
        rows.append(row)
    return rows

def main(names):
    for name in names:
        rows = []
        for f in sorted(glob.glob(ROOT + '/' + SETS[name])):
            for d in games(f):
                rows.extend(analyse(d))
        json.dump(rows, open(os.path.join(os.path.dirname(__file__), f'conv_{name}.json'), 'w'), indent=0)
        ngames = len({(r['file'], r['g']) for r in rows})
        A = [r for r in rows if 'asm_turn' in r]
        W = [r for r in A if r['won']]
        print(f"== {name}: games {ngames}; seats with lines {len(rows)}; assembled {len(A)}; won {len(W)}; lost {len(A)-len(W)}")
        print('   agents among assembled:', collections.Counter(r['agent'] for r in A))
        print('   winners methods:', collections.Counter(r['method'] for r in W))
        print('   same global turn win: %d/%d' % (sum(r['same_turn_win'] for r in W), len(W)))
        print('   winners lag (table rounds) :', sorted(r['lag_rounds'] for r in W))
        print('   same table round win: %d/%d' % (sum(1 for r in W if r['lag_rounds'] == 0), len(W)))
        if A:
            print('   asm own round median %s; lag all assembled median %s' % (statistics.median(r['asm_round'] for r in A), statistics.median(r['lag_rounds'] for r in A)))

if __name__ == '__main__':
    main(sys.argv[1:] or ['agent093', 'stock_hc'])
