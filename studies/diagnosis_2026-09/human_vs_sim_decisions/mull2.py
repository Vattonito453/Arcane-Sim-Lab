import simload,glob,collections,sys
from lines import SETS
from mull import FAST
for name in sys.argv[1:]:
    res={'stock':collections.Counter(),'plan':collections.Counter()}; ex=[]
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            draws=collections.defaultdict(list); blocks=collections.defaultdict(list)
            for r in G['stream']:
                if r.get('rec')!='zone' or r['turn']!=0: continue
                if r['from']=='Library' and r['to']=='Hand':
                    p=r['toPlayer']; draws[p].append((r['card'],r.get('types','')))
                    if len(draws[p])==7: blocks[p].append(draws[p]); draws[p]=[]
            for p,bl in blocks.items():
                ag=G['agents'].get(p,'?')
                for i,h in enumerate(bl):
                    lands=sum(1 for c,t in h if 'Land' in t); fast=sum(1 for c,t in h if c in FAST and 'Land' not in t)
                    dec='keep' if i==len(bl)-1 else 'ship'
                    res[ag][(dec, 'lands<=1' if lands<=1 else 'lands>=2', 'src>=3' if lands+fast>=3 else 'src<3', 'fast>=1' if fast else 'fast0')]+=1
                    if dec=='ship' and lands<=1 and lands+fast>=3 and len(ex)<8: ex.append((simload.bare(p),[c for c,t in h]))
    print('==',name)
    for ag,c in res.items():
        if not c: continue
        tot_ship=sum(v for k,v in c.items() if k[0]=='ship'); tot_keep=sum(v for k,v in c.items() if k[0]=='keep')
        s_good=sum(v for k,v in c.items() if k[0]=='ship' and k[1]=='lands<=1' and k[2]=='src>=3')
        k_nofast=sum(v for k,v in c.items() if k[0]=='keep' and k[3]=='fast0')
        k_lowsrc=sum(v for k,v in c.items() if k[0]=='keep' and k[2]=='src<3')
        print('  %s: hands shipped %d, of which <=1 land but >=3 mana sources: %d; hands kept %d, kept with zero fast mana: %d, kept with <3 sources: %d'%(ag,tot_ship,s_good,tot_keep,k_nofast,k_lowsrc))
    for e in ex: print('   shipped:',e)
