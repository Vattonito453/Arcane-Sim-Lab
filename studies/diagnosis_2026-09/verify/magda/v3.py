import json, glob, collections, re, statistics
BASE = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ["runs_015_default", "runs_winmax", "runs_016_engine"]
MAG = "Ai(1)-magda"
out = []
for arm in ARMS:
    for f in sorted(glob.glob(BASE + arm + "/cell_n7*.jsonl")):
        games = collections.defaultdict(lambda: dict(portal_evt=[], winner=None, turns=None, override=0, first_magda_search_turn=None, magda_search=0, portal_cast=0, portal_hand_after0=0, portal_in_hand_end=False, mull=0, magda_act_msgs=0, first_portal_bf_turn=None, portal_bf_from=None, win_turn=None))
        with open(f, encoding='utf-8') as fh:
            for line in fh:
                try: r = json.loads(line)
                except: continue
                rec = r.get('rec')
                if rec == 'meta':
                    mp = r['players'][r['agents'].index('plan')] == MAG; continue
                G = games[r.get('game')]
                if rec == 'zone' and r.get('card') == 'Portal to Phyrexia' and (r.get('toPlayer') == MAG or r.get('fromPlayer') == MAG):
                    G['portal_evt'].append((r.get('turn'), r.get('from'), r.get('to')))
                    if r.get('to') == 'Battlefield' and G['first_portal_bf_turn'] is None:
                        G['first_portal_bf_turn'] = r.get('turn'); G['portal_bf_from'] = r.get('from')
                    if r.get('to') == 'Hand' and r.get('turn',0) > 0: G['portal_hand_after0'] += 1
                elif rec == 'entry':
                    m = r.get('message','')
                    if m.startswith(MAG + ' cast Portal to Phyrexia'): G['portal_cast'] += 1
                    if m.startswith(MAG + ' activated Magda'): G['magda_act_msgs'] += 1
                elif rec == 'agent' and r.get('player') == MAG:
                    if r.get('event') == 'tutor_steer' and 'over=Portal to Phyrexia' in r.get('detail',''): G['override'] += 1
                    if r.get('event') == 'search_seen' and 'src=Magda' in r.get('detail',''):
                        G['magda_search'] += 1
                        if G['first_magda_search_turn'] is None: G['first_magda_search_turn'] = r.get('turn')
                elif rec == 'result':
                    G['winner'] = r.get('winner'); G['turns'] = r.get('turns')
        for g, G in games.items():
            if G['turns'] is None: continue
            # last known portal zone
            last = G['portal_evt'][-1][2] if G['portal_evt'] else None
            G['portal_last'] = last
            G.update(arm=arm, cell=f.split('/')[-1], game=g, magda_plan=mp)
            out.append(G)
P = [g for g in out if g['magda_plan']]; S = [g for g in out if not g['magda_plan']]
ov = [g for g in P if g['override']>0]
print("plan games with >=1 Portal override:", len(ov), "of", len(P), "; wins in those", sum(g['winner']==MAG for g in ov), "; portal landed in those", sum(g['first_portal_bf_turn'] is not None for g in ov))
print("plan games without override:", len(P)-len(ov), "wins", sum(g['winner']==MAG for g in P if g['override']==0))
print("overrides per game dist", collections.Counter(g['override'] for g in P))
print("plan: magda activations msgs games>0:", sum(g['magda_act_msgs']>0 for g in P), " stock:", sum(g['magda_act_msgs']>0 for g in S), "of", len(S))
print("plan: magda search games>0:", sum(g['magda_search']>0 for g in P))
for lab, R in (("plan",P),("stock",S)):
    pb = [g for g in R if g['first_portal_bf_turn'] is not None]
    print(lab, "portal_bf from:", collections.Counter(g['portal_bf_from'] for g in pb), "cast from hand:", sum(g['portal_cast']>0 for g in R), "portal to hand after t0:", sum(g['portal_hand_after0']>0 for g in R), "portal last zone Hand:", sum(g['portal_last']=='Hand' for g in R))
    if pb:
        print("   median portal bf turn (player-turns):", statistics.median(g['first_portal_bf_turn'] for g in pb))
# plan games where Portal in hand at end
for g in P:
    if g['portal_hand_after0'] or g['portal_last']=='Hand':
        print("  plan portal-in-hand game", g['arm'], g['game'], g['portal_evt'][:6], 'cast', g['portal_cast'], 'won', g['winner']==MAG, 'turns', g['turns'])
print("---- conditional on Magda activating her tutor ----")
for lab, R in (("plan",P),("stock",S)):
    A = [g for g in R if g['magda_act_msgs']>0]; N = [g for g in R if g['magda_act_msgs']==0]
    print(lab, "act games", len(A), "wins", sum(g['winner']==MAG for g in A), "portal landed", sum(g['first_portal_bf_turn'] is not None for g in A),
          "| no-act games", len(N), "wins", sum(g['winner']==MAG for g in N))
    if A: print("   median first magda activation turn:", statistics.median(g['first_magda_search_turn'] for g in A if g['first_magda_search_turn'] is not None) if lab=='plan' else '')
    for arm in ARMS:
        AA=[g for g in A if g['arm']==arm]; RR=[g for g in R if g['arm']==arm]
        print("    ", arm, "games", len(RR), "wins", sum(g['winner']==MAG for g in RR), "act", len(AA), "act wins", sum(g['winner']==MAG for g in AA))
