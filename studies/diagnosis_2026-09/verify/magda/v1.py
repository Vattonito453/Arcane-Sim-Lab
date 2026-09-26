import json, glob, collections, re, statistics
BASE = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ["runs_015_default", "runs_winmax", "runs_016_engine"]
MAG = "Ai(1)-magda"
def parse_detail(d):
    out = {}
    # keys are k=v separated by space; values may contain spaces; parse by known keys
    keys = re.findall(r'(\w+)=', d)
    parts = re.split(r'\s(?=\w+=)', d)
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1); out[k] = v
    return out

rows = []  # per game rows
search = collections.Counter()
steers = collections.Counter()
overrides = collections.defaultdict(collections.Counter)
evc = collections.Counter()
for arm in ARMS:
    for f in sorted(glob.glob(BASE + arm + "/cell_n7*.jsonl")):
        meta = None
        games = {}
        with open(f, encoding='utf-8') as fh:
            for line in fh:
                try: r = json.loads(line)
                except: continue
                rec = r.get('rec')
                if rec == 'meta':
                    meta = r; plan_player = r['players'][r['agents'].index('plan')]
                    magda_plan = (plan_player == MAG)
                    continue
                g = r.get('game')
                G = games.setdefault(g, dict(portal_bf=False, portal_bf_turn=None, portal_hand=False, winner=None, turns=None, fetched=False, steer_over_portal=0, magda_src_portal_pick=0, end=None))
                if rec == 'zone' and r.get('card') == 'Portal to Phyrexia':
                    if r.get('to') == 'Battlefield' and r.get('toPlayer') == MAG and not G['portal_bf']:
                        G['portal_bf'] = True; G['portal_bf_turn'] = r.get('turn'); G['portal_from'] = r.get('from')
                    if r.get('to') == 'Hand' and r.get('toPlayer') == MAG:
                        G['portal_hand'] = True
                elif rec == 'result':
                    G['winner'] = r.get('winner'); G['turns'] = r.get('turns'); G['draw']=r.get('draw'); G['end']=r
                elif rec == 'agent' and r.get('player') == MAG:
                    ev = r.get('event'); d = r.get('detail','')
                    evc[(arm, ev)] += 1
                    if ev == 'search_seen':
                        p = parse_detail(d)
                        src = p.get('src',''); picked = p.get('picked','')
                        search[(arm, src.startswith('Magda'), picked == 'Portal to Phyrexia', p.get('agree'))] += 1
                        if src.startswith('Magda') and picked == 'Portal to Phyrexia':
                            G['magda_src_portal_pick'] += 1
                    if ev == 'tutor_steer':
                        p = parse_detail(d)
                        if p.get('over') == 'Portal to Phyrexia':
                            G['steer_over_portal'] += 1
                            overrides[(arm, p.get('mode'))][p.get('steer')] += 1
        for g, G in games.items():
            if G['end'] is None: continue
            G.update(arm=arm, file=f.split('/')[-1], game=g, magda_plan=magda_plan)
            rows.append(G)
json.dump([{k:v for k,v in r.items() if k!='end'} for r in rows], open(r"C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad/diagnosis/verify/magda/rows.json","w"))
print("games", len(rows))
for mp in (True, False):
    R = [r for r in rows if r['magda_plan'] == mp]
    w = sum(1 for r in R if r['winner'] == MAG)
    pb = [r for r in R if r['portal_bf']]
    pw = sum(1 for r in pb if r['winner'] == MAG)
    npb = [r for r in R if not r['portal_bf']]
    npw = sum(1 for r in npb if r['winner'] == MAG)
    dec = sum(1 for r in R if r['winner'])
    print(f"magda_plan={mp}: games={len(R)} decided={dec} magda_wins={w} ({w/len(R):.3f}; of decided {w/max(dec,1):.3f}) portal_bf={len(pb)} ({len(pb)/len(R):.3f}) win_w_portal={pw} win_wo_portal={npw}/{len(npb)} portal_hand={sum(r['portal_hand'] for r in R)}")
    for arm in ARMS:
        RA = [r for r in R if r['arm']==arm]
        print("   ", arm, len(RA), "wins", sum(r['winner']==MAG for r in RA), "portal_bf", sum(r['portal_bf'] for r in RA), "portal_hand", sum(r['portal_hand'] for r in RA))
print("search_seen (arm, srcMagda, pickedPortal, agree):")
for k, v in sorted(search.items()): print("  ", k, v)
print("overrides:")
for k, v in overrides.items(): print("  ", k, sum(v.values()), dict(v))
print("events per arm:")
for k,v in sorted(evc.items()): print("  ",k,v)
