import simload,glob,collections,re,sys,json
from lines import SETS
from simload import bare
KEPT=re.compile(r"^(.+?) has kept a hand of (\d+) cards")
FAST={"Sol Ring","Mana Crypt","Mana Vault","Chrome Mox","Mox Diamond","Mox Opal","Mox Amber","Lotus Petal","Jeweled Lotus","Lion's Eye Diamond","Simian Spirit Guide","Elvish Spirit Guide","Dark Ritual","Cabal Ritual","Rite of Flame","Desperate Ritual","Pyretic Ritual","Seething Song","Arcane Signet","Fellwar Stone","Grim Monolith","Basalt Monolith","Springleaf Drum","Talisman of Dominance","Talisman of Creativity","Talisman of Curiosity","Talisman of Indulgence","Talisman of Progress","Talisman of Conviction","Birds of Paradise","Llanowar Elves","Elvish Mystic","Fyndhorn Elves","Noble Hierarch","Ignoble Hierarch","Delighted Halfling","Deathrite Shaman","Elves of Deep Shadow","Boreal Druid","Gemstone Caverns","Paradise Mantle","Relic of Legends","Treasonous Ogre","Culling the Weak","Wild Growth","Utopia Sprawl","Carpet of Flowers","Mox Tantalite","Lotus Cobra","Dockside Extortionist"}
for name in sys.argv[1:]:
    kept=collections.Counter(); byagent=collections.defaultdict(collections.Counter)
    shipped=collections.Counter(); keptq=collections.Counter()
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            for e in G['entries']:
                if e['type']=='MULLIGAN':
                    m=KEPT.match(e['message'])
                    if m: byagent[G['agents'].get(m.group(1),'?')][int(m.group(2))]+=1
            # reconstruct each seen opening hand from turn-0 zone records
            hands=collections.defaultdict(list); cur=collections.defaultdict(list)
            for r in G['stream']:
                if r.get('rec')=='zone' and r['turn']==0:
                    p=r.get('toPlayer') or r.get('fromPlayer')
                    if r['from']=='Library' and r['to']=='Hand': cur[r['toPlayer']].append((r['card'],r.get('types','')))
                    if r['from']=='Hand' and r['to']=='Library':
                        if len(cur[r['fromPlayer']])>=7: hands[r['fromPlayer']].append(cur[r['fromPlayer']][:7]); cur[r['fromPlayer']]=cur[r['fromPlayer']][7:] if len(cur[r['fromPlayer']])>7 else []
                if r.get('rec')=='agent' and r.get('event') in('mull_take','mull_keep') and r['turn']==0:
                    p=r['player']
                    # the hand being judged = last 7 drawn
                    h=cur[p][-7:] if len(cur[p])>=7 else cur[p]
                    lands=sum(1 for c,t in h if 'Land' in t); fast=sum(1 for c,t in h if c in FAST and 'Land' not in t)
                    src=lands+fast
                    key=('take' if r['event']=='mull_take' else 'keep', 'lands=%d'%lands, 'sources>=3' if src>=3 else 'sources<3')
                    (shipped if r['event']=='mull_take' else keptq)[(lands, min(fast,3))]+=1
    print('==',name)
    for ag,c in byagent.items():
        tot=sum(c.values()); print('  %s kept sizes'%ag, dict(sorted(c.items(),reverse=True)), 'n=%d; kept<=5: %.1f%%; kept<=4: %.1f%%'%(tot,100*sum(v for k,v in c.items() if k<=5)/tot,100*sum(v for k,v in c.items() if k<=4)/tot))
    if shipped:
        print('  agent SHIPPED hands by (lands, fast-mana nonland up to 3):',dict(sorted(shipped.items())))
        s13=sum(v for (l,f),v in shipped.items() if l<=1 and l+f>=3)
        print('  shipped hands with <=1 land but >=3 total mana sources (lands+fast mana): %d of %d'%(s13,sum(shipped.values())))
        k=sum(v for (l,f),v in keptq.items() if f==0 and l>=2)
        print('  agent KEPT hands with zero fast mana: %d of %d'%(k,sum(keptq.values())))
