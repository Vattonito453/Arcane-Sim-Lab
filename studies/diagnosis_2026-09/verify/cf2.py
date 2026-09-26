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
        ak=[x[3] for r in rs for x in r.get('lines_first',[]) if KILL.search(';'.join(x[1]))]
        c=min([w]+a); ck=min([w]+ak)
        act.append(w); cf.append(c); cfk.append(ck); faster+= c<w; fasterk+= ck<w
    A=[r for r in R if 'asm_turn' in r]
    killseat=[r for r in A if any(KILL.search(';'.join(x[1])) for x in r['lines_first'])]
    print(n,'decided',dec,'actual mean %.1f -> any-line cf %.1f (faster %d) ; kill-line cf %.1f (faster %d)'%(statistics.mean(act),statistics.mean(cf),faster,statistics.mean(cfk),fasterk))
    print('   assembled seats %d; of which ever assembled a kill-clause line %d (won %d); resource-only %d (won %d)'%(len(A),len(killseat),sum(r['won'] for r in killseat),len(A)-len(killseat),sum(r['won'] for r in A if r not in killseat)))
    for r in killseat:
        kl=[x for x in r['lines_first'] if KILL.search(';'.join(x[1]))]
        print('     ',r['deck'],'W' if r['won'] else 'L',r['method'],'| kill line first asm own-round',min(x[3] for x in kl),'| game end own round',r['own_round_end'], '| table lag', r['table_round_end']-min(x[4] for x in kl), '|', kl[0][0])
