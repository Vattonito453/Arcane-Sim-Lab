import json,collections,statistics,sys,re
KILL=re.compile(r"Win the game|damage|combat phases|lose the game|loses life|life loss|Near-infinite mill|Infinite mill|each opponent", re.I)
for n in sys.argv[1:]:
    R=json.load(open(f'conv_{n}.json'))
    G=collections.defaultdict(list)
    for r in R: G[(r['file'],r['g'])].append(r)
    act=[];cf=[];cfk=[];faster=0;fasterk=0;dec=0
    for k,rs in G.items():
        w=rs[0]['win_round']
        if not rs[0]['winner']: continue
        dec+=1
        a=[r['asm_round'] for r in rs if 'asm_turn' in r]
        ak=[]
        for r in rs:
            if 'asm_turn' not in r: continue
            # earliest assembly of a KILL line: need all lines w/ produces; approximate with first-assembled lines only
            if any(KILL.search(';'.join(p)) for L,p in r['asm_lines']): ak.append(r['asm_round'])
        c=min([w]+a); ck=min([w]+ak)
        act.append(w); cf.append(c); cfk.append(ck); faster+= c<w; fasterk+= ck<w
    print(n,'decided',dec,'actual mean %.1f -> any-line cf %.1f (faster %d) ; kill-line cf %.1f (faster %d)'%(statistics.mean(act),statistics.mean(cf),faster,statistics.mean(cfk),fasterk))
