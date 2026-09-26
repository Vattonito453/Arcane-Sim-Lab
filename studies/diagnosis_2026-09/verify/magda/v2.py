import json, glob, collections, re
BASE = r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability/"
ARMS = ["runs_015_default", "runs_winmax", "runs_016_engine"]
MAG = "Ai(1)-magda"
out = []
for arm in ARMS:
    for f in sorted(glob.glob(BASE + arm + "/cell_n7*.jsonl")):
        games = collections.defaultdict(lambda: dict(clock_act=0, targets=collections.Counter(), clock_bf=False, clock_bf_turn=None, torque_bf=False, auto_bf=set(), winner=None, treasure_tokens=0, magda_act=0, portal_bf=False, clock_via_lib=0, steer_clock=0, turns=None, win_turn=None))
        with open(f, encoding='utf-8') as fh:
            for line in fh:
                try: r = json.loads(line)
                except: continue
                rec = r.get('rec')
                if rec == 'meta':
                    plan_player = r['players'][r['agents'].index('plan')]
                    mp = plan_player == MAG; continue
                G = games[r.get('game')]
                if rec == 'entry':
                    m = r.get('message','')
                    if m.startswith(MAG + ' activated Clock of Omens'):
                        G['clock_act'] += 1
                        t = re.search(r'targeting \[(.*?) \(\d+\)', m)
                        G['targets'][t.group(1) if t else '-'] += 1
                    if m.startswith(MAG + ' activated Magda'):
                        G['magda_act'] += 1
                elif rec == 'zone':
                    if r.get('to') == 'Battlefield' and r.get('toPlayer') == MAG:
                        c = r.get('card')
                        if c == 'Clock of Omens':
                            G['clock_bf'] = True
                            if r.get('from') == 'Library': G['clock_via_lib'] += 1
                            if G['clock_bf_turn'] is None: G['clock_bf_turn'] = r.get('turn')
                        if c == 'Liquimetal Torque': G['torque_bf'] = True
                        if c in ('Universal Automaton','Metallic Mimic','Adaptive Automaton','Roaming Throne','Barkform Harvester','Three Tree Mascot'): G['auto_bf'].add(c)
                        if c == 'Portal to Phyrexia': G['portal_bf'] = True
                        if r.get('token') and 'Treasure' in c: G['treasure_tokens'] += 1
                elif rec == 'agent' and r.get('player') == MAG and r.get('event') == 'tutor_steer' and 'steer=Clock of Omens' in r.get('detail',''):
                    G['steer_clock'] += 1
                elif rec == 'result':
                    G['winner'] = r.get('winner'); G['turns'] = r.get('turns')
        for g, G in games.items():
            if G['winner'] is None and G['turns'] is None: continue
            G['arm']=arm; G['cell']=f.split('/')[-1]; G['game']=g; G['magda_plan']=mp
            out.append(G)
for mp in (True, False):
    R = [g for g in out if g['magda_plan']==mp]
    act = [g for g in R if g['clock_act']>0]
    print(f"magda_plan={mp} games={len(R)} clock_bf={sum(g['clock_bf'] for g in R)} clock_from_library={sum(1 for g in R if g['clock_via_lib'])} games_with_clock_activation={len(act)} total_acts={sum(g['clock_act'] for g in R)} wins_in_act_games={sum(g['winner']==MAG for g in act)}")
    tg = collections.Counter()
    for g in act: tg.update(g['targets'])
    print("   targets:", tg.most_common(10))
    # clock + enabler assembled
    asm = [g for g in R if g['clock_bf'] and (g['torque_bf'] or g['auto_bf'])]
    print(f"   clock+enabler both landed: {len(asm)} wins {sum(g['winner']==MAG for g in asm)}; max treasure tokens in a game {max((g['treasure_tokens'] for g in R), default=0)}")
    for g in sorted(act, key=lambda x:-x['clock_act'])[:12]:
        print("     ", g['arm'], g['cell'], g['game'], 'acts', g['clock_act'], 'torque', g['torque_bf'], 'auto', sorted(g['auto_bf']), 'treasures', g['treasure_tokens'], 'magdaAct', g['magda_act'], 'won', g['winner']==MAG, 'winner', g['winner'], 'steerClock', g['steer_clock'])
