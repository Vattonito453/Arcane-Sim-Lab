import json, glob, collections, re, os, hashlib
files = glob.glob('studies/**/*.jsonl', recursive=True)
print('jsonl files', len(files))
seen_hash=set(); dup=0
cc=collections.Counter(); tc=collections.Counter(); n_cc=0; n_files_cc=0
decks_with=collections.Counter()
plan_seat_games=0
for f in files:
    h=hashlib.md5(open(f,'rb').read()).hexdigest()
    if h in seen_hash: dup+=1; continue
    seen_hash.add(h)
    got=False
    with open(f,encoding='utf-8',errors='replace') as fh:
        for line in fh:
            if '"combo_cast"' not in line and '"tutor_cast"' not in line: continue
            try: r=json.loads(line)
            except: continue
            if r.get('rec')!='agent': continue
            d=r.get('detail','')
            name=re.split(r' \(', d)[0]
            if r['event']=='combo_cast': cc[name]+=1; n_cc+=1; got=True
            else: tc[d.split(' seeking ')[-1] if ' seeking ' in d else d]+=1
    n_files_cc+=got
print('dup files skipped', dup)
print('combo_cast total', n_cc, 'files with any', n_files_cc)
for k in ['Brain Freeze','Underworld Breach',"Lion's Eye Diamond","Thassa's Oracle",'Demonic Consultation','Tainted Pact','Clock of Omens','Kiki-Jiki, Mirror Breaker','Emiel the Blessed','Dramatic Reversal','Isochron Scepter','Wheel of Fortune',"Jeska's Will",'Lotus Petal','Portal to Phyrexia']:
    print(f'  {k}: {cc[k]}   tutor_cast seeking: {tc[k]}')
print('top 25', cc.most_common(25))
