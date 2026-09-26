import simload, glob, collections, re, sys
from lines import SETS
from simload import bare
KEY=["Thassa's Oracle","Demonic Consultation","Tainted Pact","Underworld Breach","Brain Freeze","Lion's Eye Diamond","Jeska's Will","Ad Nauseam","Grapeshot","Windfall","Wheel of Fortune","Necropotence","Past in Flames","Aetherflux Reservoir","Doomsday"]
for name in sys.argv[1:]:
    cast=collections.Counter(); wins=collections.Counter(); ocases=collections.Counter()
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            w=simload.win_info(G)
            # casts by turn from entries
            byturn=collections.defaultdict(list)
            for e in G['entries']:
                if e.get('type')=='STACK_ADD':
                    m=re.match(r'^(Ai\(\d\)-\S+) cast (.+?)(?: targeting.*)?$', e['message'], re.S)
                    if m and m.group(2) in KEY:
                        cast[m.group(2)]+=1; byturn[(m.group(1),e['_turn'])].append(m.group(2))
            for (p,t),cs in byturn.items():
                if "Thassa's Oracle" in cs:
                    exile = any(x in cs for x in ("Demonic Consultation","Tainted Pact"))
                    won = w['winner']==p and w['method'].startswith('spell:Thassa') and t==G['last_turn']
                    ocases[('with exile-spell same turn' if exile else 'no exile spell that turn', 'won' if won else 'no win')]+=1
            if w['method'].startswith('spell:'): wins[w['method']]+=1
    print('==',name); print('  casts',dict(cast)); print('  spell wins',dict(wins)); print('  oracle casts',dict(ocases))
