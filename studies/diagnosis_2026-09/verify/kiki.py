import json,glob,re,collections,os
os.chdir(r'C:/Users/Vatto/Magic Rules Engine/studies')
UNTAPPERS={'Zealous Conscripts','Pestermite','Deceiver Exarch','Felidar Guardian','Restoration Angel','Village Bell-Ringer','Combat Celebrant','Resolute Blademaster','Breaching Hippocamp','Bounding Krasis','Corridor Monitor','Karmic Guide'}
c=collections.Counter(); rows=[]
seen=set()
for f in glob.glob('**/*.jsonl',recursive=True):
    try: txt=open(f,encoding='utf-8').read()
    except: continue
    if 'activated Kiki-Jiki' not in txt and 'Splinter Twin' not in txt: continue
    E=[]
    for l in txt.splitlines():
        try: r=json.loads(l)
        except: continue
        if r.get('rec')=='entry': E.append(r)
    for i,e in enumerate(E):
        m=e['message']
        mt=re.match(r'(\S+) activated Kiki-Jiki, Mirror Breaker targeting \[(.+?) \(\d+\)\]',m)
        if not mt: continue
        tgt=mt.group(2)
        c[('kiki_act',)]+=1
        if tgt not in UNTAPPERS: continue
        # find the copy trigger
        trig=None
        for x in E[i+1:i+10]:
            if x['type']=='STACK_ADD' and f'triggered {tgt}' in x['message']:
                mm=re.search(r'targeting \[(.+?) \(\d+\)\]',x['message']); trig=mm.group(1) if mm else '(no target)'; break
        key=(os.path.basename(f),e['game'],e['seq'])
        c[('untapper',tgt,'kiki' if trig=='Kiki-Jiki, Mirror Breaker' else ('none' if trig is None else 'other'))]+=1
        rows.append((os.path.dirname(f),os.path.basename(f),e['game'],e['seq'],tgt,trig))
for k,v in sorted(c.items(),key=str): print(k,v)
for r in rows: print(r)
