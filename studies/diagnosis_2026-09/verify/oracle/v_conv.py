"""For every plan combo_cast, did the plan seat win that game, and how/when?
Also: does every Oracle win have an in-response Consultation?"""
import collections, glob, json, re
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
SETS = ["agent_viability/runs_015_default/cell_*.jsonl","agent_viability/runs_winmax/cell_*.jsonl","agent_viability/runs_016_engine/cell_*.jsonl","behavior_rubric/runs_agent_shipping/*.jsonl","tutor_targeting/runs_stage2/*.jsonl","behavior_rubric/runs_agent_093/*.jsonl","behavior_rubric/runs_agent/*.jsonl"]
cc = collections.Counter()
winsame = collections.Counter()
oracle_win_resp = collections.Counter()
last_cc_before_win = collections.Counter()
for pat in SETS:
    for f in glob.glob(S+pat):
        meta=None; games=collections.defaultdict(list); ag=collections.defaultdict(list)
        for l in open(f,encoding='utf-8'):
            try: r=json.loads(l)
            except: continue
            if r.get('rec')=='meta': meta=r
            elif r.get('rec')=='entry': games[r['game']].append(r)
            elif r.get('rec')=='agent': ag[r['game']].append(r)
        if not meta: continue
        agents=dict(zip(meta['players'],meta['agents']))
        for g,es in games.items():
            es.sort(key=lambda r:r['seq'])
            last=0; won=None
            for e in es:
                if e['type']=='TURN': last=int(re.match(r'Turn (\d+)',e['message']).group(1))
                m=re.match(r"(Ai\(\d\)-\S+) has won (.*)",e['message'])
                if m and e['type']=='GAME_OUTCOME': won=(m.group(1),m.group(2),last)
            for a in ag[g]:
                if a['event']!='combo_cast': continue
                piece=a['detail'].split(' (')[0]
                cc[piece]+=1
                if won and won[0]==a['player'] and agents.get(a['player'])=='plan':
                    how='oracle' if 'Thassa' in won[1] else 'other'
                    if won[2]-a['turn']<=0:
                        winsame[(piece,how)]+=1
            if won and 'Thassa' in won[1]:
                # in-response Consultation?
                open_t=False; resp=False
                for e in es:
                    if e['type']=='STACK_ADD' and re.match(re.escape(won[0])+r" triggered Thassa's Oracle",e['message']): open_t=True
                    if e['type']=='STACK_RESOLVE' and e['message'].startswith("When Thassa's Oracle enters"): open_t=False
                    if e['type']=='STACK_ADD' and open_t and e['message'].startswith(won[0]+" cast Demonic Consultation"): resp=True
                oracle_win_resp[resp]+=1
            if won and agents.get(won[0])=='plan' and 'Thassa' not in won[1]:
                ccs=[a for a in ag[g] if a['event']=='combo_cast' and a['player']==won[0] and a['turn']==won[2]]
                last_cc_before_win[tuple(sorted(set(a['detail'].split(' (')[0] for a in ccs)))]+=1
print("combo_cast pieces:", cc.most_common(40))
print("plan combo_cast on the turn the same seat won:", dict(winsame))
print("Oracle wins with in-response Consultation:", dict(oracle_win_resp))
print("plan non-Oracle wins: combo_cast pieces on the winning turn:", last_cc_before_win.most_common(15))
