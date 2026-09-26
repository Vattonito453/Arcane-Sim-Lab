import json, glob, collections
FRONTS = ["Sink into Stupor","Shatterskull Smashing","Birgi, God of Storytelling","Pinnacle Monk","Emeria's Call","Invasion of Ikoria","Sea Gate Restoration","Ral, Monsoon Mage","Flamescroll Celebrant","Bridgeworks Battle","Turntimber Symbiosis","Sundering Eruption","Hydroelectric Specimen","Esika, God of the Tree","Duskwatch Recruiter","Disciple of Freyalise"]
res = collections.defaultdict(lambda: [0,0,collections.Counter(),set()])
for f in glob.glob('studies/**/*.jsonl', recursive=True):
    d = f.replace(chr(92),'/').rsplit('/',1)[0]
    head = open(f, encoding='utf-8', errors='replace').readline()
    try: meta=json.loads(head)
    except: continue
    if meta.get('rec')!='meta': continue
    decks = meta.get('decks') or []
    if not any('human_ceiling' in (x or '') or 'simlab-runs/hc_' in (x or '') for x in decks): continue
    r = res[d]; r[0]+=1
    for l in open(f, encoding='utf-8', errors='replace'):
        if '"rec":"zone"' in l or '"rec":"entry"' in l:
            for n in FRONTS:
                if n in l: r[2][n]+=1
        if '"rec":"result"' in l: r[1]+=1
for d,(nf,ng,c,_) in sorted(res.items()):
    print(f"{d}: files={nf} games={ng} DFC-front mentions={sum(c.values())} {dict(c) if c else ''}")
