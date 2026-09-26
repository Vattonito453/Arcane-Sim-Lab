import json, glob, collections
DROPPED = {"Sink into Stupor // Soporific Springs","Shatterskull Smashing // Shatterskull, the Hammer Pass","Birgi, God of Storytelling // Harnfel, Horn of Bounty","Pinnacle Monk // Mystic Peak","Emeria's Call // Emeria, Shattered Skyclave","Invasion of Ikoria // Zilortha, Apex of Ikoria","Sea Gate Restoration // Sea Gate, Reborn","Ral, Monsoon Mage // Ral, Leyline Prodigy","Flamescroll Celebrant // Revel in Silence","Bridgeworks Battle // Tanglespan Bridgeworks","Turntimber Symbiosis // Turntimber, Serpentine Wood","Sundering Eruption // Volcanic Fissure","Hydroelectric Specimen // Hydroelectric Laboratory","Esika, God of the Tree // The Prismatic Bridge","Duskwatch Recruiter // Krallenhorde Howler","Disciple of Freyalise // Garden of Freyalise"}
hits = collections.defaultdict(set); files=0; other=collections.defaultdict(set)
for f in glob.glob('studies/**/plans*.json', recursive=True) + glob.glob('studies/**/*plan*.json', recursive=True):
    try: d = json.load(open(f, encoding='utf-8'))
    except Exception as e: continue
    files += 1
    d = d.get("decks", d) if isinstance(d, dict) else d
    items = d.items() if isinstance(d, dict) else []
    for deck, plan in items:
        if not isinstance(plan, dict): continue
        for ln in plan.get('lines', []) or []:
            cs = ln.get('cards', []) if isinstance(ln, dict) else []
            bad = [c for c in cs if c in DROPPED]
            if bad: hits[(deck, ' + '.join(cs))].add(f.split('studies')[-1][1:40])
        for fld in ('tutors',):
            for c in plan.get(fld, []) or []:
                if c in DROPPED: other[(deck, fld, c)].add(f.split('studies')[-1][1:40])
        for c in ((plan.get('search') or {}).get('targets') or {}):
            if c in DROPPED: other[(deck,'search_target',c)].add(f.split('studies')[-1][1:40])
        for c in (plan.get('weights') or {}):
            if c in DROPPED: other[(deck,'weight',c)].add('x')
print('plan files scanned', files)
for k, v in sorted(hits.items()): print('LINE', k, len(v), sorted(v)[:4])
for k, v in sorted(other.items()): print('OTHER', k, len(v))
