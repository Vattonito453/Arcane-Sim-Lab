import simload,glob,collections,statistics,sys
from lines import SETS
from simload import bare
HUMAN={'magda':[1,2],'tymna_thrasios':[2,2],'rog_ishai':[1,1],'selvala_archetype':[4],'joseph_ral':[2,2],'rograkh_silas':[2],'derevi':[3],'cabbage_merchant':[2,2,1,2],'malcolm_kediss':[2],'kinnan':[2,3,3],'yidris':[2,2],'rog_thrasios':[1,1,1],'isaac_yisan':[1],'lily_malcolm_vial':[2],'matt_sisay':[4],'alan_tnt':[2],'dallas_bluefarm':[3],'winota_rachel':[1,3],'winota_lua':[2,2],'winota_mike':[3],'winota_ian':[2]}
for name in sys.argv[1:]:
    per=collections.defaultdict(list); never=collections.Counter(); total=collections.Counter()
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            first={}
            for r in G['stream']:
                if r.get('rec')=='zone' and r['from']=='Command' and r['to'] in('Stack','Battlefield'):
                    p=r['fromPlayer']
                    if p not in first: first[p]=simload.player_round(G,p,r['turn'])
            for p in G['players']:
                d=bare(p)
                if name.startswith('av') and G['agents'].get(p)!='plan': continue
                total[d]+=1
                if p in first: per[d].append(first[p])
                else: never[d]+=1
    print('==',name)
    allsim=[]; allhum=[]
    for d in sorted(per, key=lambda d: d):
        if d in HUMAN:
            allsim+=per[d]; allhum+=HUMAN[d]
            print('  %-20s sim median %4s mean %4.1f (never cast %d/%d) | human %s'%(d,statistics.median(per[d]),statistics.mean(per[d]),never[d],total[d],HUMAN[d]))
    print('  decks with human data: sim mean %.2f (n=%d)  human mean %.2f (n=%d)'%(statistics.mean(allsim),len(allsim),statistics.mean(allhum),len(allhum)))
