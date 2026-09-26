import simload,glob,collections,re,statistics,sys
from lines import SETS, analyse
from simload import bare
ACT=re.compile(r"^(Ai\(\d\)-\S+) activated (.+?)(?: targeting .*)?$", re.S)
for name in sys.argv[1:]:
    per=[]; ex=collections.Counter(); zero=0; n=0
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            lines,fo,fa,at=analyse(G)
            acts=collections.Counter()
            for e in G['entries']:
                if e['type']=='STACK_ADD':
                    m=ACT.match(e['message'])
                    if m: acts[(m.group(1),m.group(2),e['_turn'])]+=1
            for (p,L),turns in at.items():
                # only the line-owner's own turns while assembled
                own=[t for t in turns if G['turn_player'].get(t)==p]
                if not own: continue
                n+=1
                tot=sum(acts[(p,c,t)] for t in own for c in L)
                per.append(tot/len(own))
                if tot==0: zero+=1
                ex[(bare(p),' + '.join(L))]+=0
    print('== %s: assembled (seat,line) pairs with >=1 own turn assembled: %d; mean activations of line cards per own assembled turn %.2f; pairs with ZERO line-card activations while assembled: %d'%(name,n,statistics.mean(per) if per else 0,zero))
