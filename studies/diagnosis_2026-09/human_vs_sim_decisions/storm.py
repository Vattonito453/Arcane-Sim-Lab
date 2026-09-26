import simload,glob,collections,re,sys,statistics
from lines import SETS
from simload import bare
ADD=re.compile(r"^(Ai\(\d\)-\S+) cast ")
DECKS={'joseph_ral','tyler_bluefarm','ashton_bluefarm','dallas_bluefarm','sterling_bluefarm','alan_tnt','rograkh_silas','rog_ishai','tymna_thrasios'}
for name in sys.argv[1:]:
    mx=collections.defaultdict(list); act=collections.defaultdict(list)
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            cnt=collections.Counter()
            for e in G['entries']:
                if e['type']=='STACK_ADD':
                    m=ADD.match(e['message'])
                    if m: cnt[(m.group(1),e['_turn'])]+=1
            best=collections.Counter()
            for (p,t),v in cnt.items():
                best[p]=max(best[p],v)
            for p in G['players']:
                if bare(p) in DECKS: mx[bare(p)].append(best[p])
    print('==',name)
    for d,v in sorted(mx.items()): print('  %-18s max spells in one turn per game: median %s, max %s, games>=10: %d/%d'%(d,statistics.median(v),max(v),sum(x>=10 for x in v),len(v)))
