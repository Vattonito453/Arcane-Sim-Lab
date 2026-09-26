import json, re, collections
from pathlib import Path
BASE=Path(r"C:/Users/Vatto/Magic Rules Engine/studies/agent_viability")
PIECES=("Demonic Consultation","Thassa's Oracle","Tainted Pact")
stat=collections.Counter()
for arm in ['runs_015_default','runs_winmax','runs_016_engine']:
    for f in sorted((BASE/arm).glob('cell_*rot3.jsonl')):
        games=collections.defaultdict(lambda:{'ev':[],'oraclewin':False,'winner':None,'cons':False})
        meta=None
        for line in open(f,encoding='utf-8'):
            r=json.loads(line)
            if r.get('rec')=='meta': meta=r; continue
            g=r.get('game'); G=games[g]
            if r.get('rec')=='agent': G['ev'].append((r['event'],r['detail']))
            elif r.get('rec')=='entry' and r['type']=='GAME_OUTCOME' and "won due to effect of 'Thassa's Oracle'" in r['message']: G['oraclewin']=True
            elif r.get('rec')=='entry' and r['type']=='STACK_ADD' and 'cast Demonic Consultation' in r['message']: G['cons']=True
            elif r.get('rec')=='result': G['winner']=r.get('winner')
        plan=[p for p,a in zip(meta['players'],meta['agents']) if a=='plan'][0]
        for g,G in games.items():
            if G['winner']!=plan: continue
            steer=[d for e,d in G['ev'] if e=='tutor_steer' and any(('steer='+p) in d for p in PIECES)]
            tcast=[d for e,d in G['ev'] if e=='tutor_cast' and any(p in d for p in PIECES)]
            stat[('win', 'oracle' if G['oraclewin'] else 'other', 'tutor->piece' if (steer or tcast) else 'no tutor->piece')]+=1
for k,v in sorted(stat.items()): print(v,k)
