import simload,glob,collections,re,sys
from lines import SETS, game_lines
from tutor import GENERIC
from simload import bare
RES=re.compile(r"^(.+?) \((\d+)\) - Counter (.+?) \((\d+)\)")
ADD=re.compile(r"^(Ai\(\d\)-\S+) (cast|activated|triggered) (.+?)(?: targeting .*)?$", re.S)
PROT={"Force of Will","Force of Negation","Pact of Negation","Fierce Guardianship","Deflecting Swat","Mental Misstep","Flusterstorm","Swan Song","Spell Pierce","Mindbreak Trap","Counterspell","Mana Drain","Dispel","Stern Scolding","Silence","Grand Abolisher","Veil of Summer","Autumn's Veil","Red Elemental Blast","Pyroblast","Hydroblast","Blue Elemental Blast","An Offer You Can't Refuse","Miscast","Tibalt's Trickery","Stubborn Denial","Arcane Denial","Mystic Confluence","Delay","Misdirection","Commandeer","Snapback","Borne Upon a Wind","Orim's Chant","Narset's Reversal"}
for name in sys.argv[1:]:
    res=collections.Counter()
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            lines=game_lines(G)
            # hand state at each Hand->Stack of cardId: map (player, card, turn)-> protection cards in hand
            hand=collections.defaultdict(collections.Counter); held={}
            for r in G['stream']:
                if r.get('rec')!='zone': continue
                c=r['card']; fp=r.get('fromPlayer'); tp=r.get('toPlayer')
                if r['from']=='Hand' and fp:
                    if r['to']=='Stack': held[(fp,c,r['turn'])]=[x for x,v in hand[fp].items() if v>0 and x in PROT and x!=c]
                    hand[fp][c]-=1
                if r['to']=='Hand' and tp: hand[tp][c]+=1
            owner={}; name_={}; addidx={}
            E=G['entries']
            for i,e in enumerate(E):
                if e['type']=='STACK_ADD':
                    m=ADD.match(e['message'])
                    if m and m.group(2)=='cast' and e.get('cardId') is not None:
                        owner[e['cardId']]=m.group(1); name_[e['cardId']]=m.group(3); addidx[e['cardId']]=i
                if e['type']=='STACK_RESOLVE':
                    m=RES.match(e['message'])
                    if not m: continue
                    cid=int(m.group(2)); tid=int(m.group(4)); tname=m.group(3)
                    P=owner.get(cid); Q=owner.get(tid)
                    if not P or not Q or P==Q: continue
                    if not (any(tname in L for L in lines[Q]) or tname in simload.commanders(G['pod'],bare(Q))): continue
                    ag=G['agents'].get(Q,'?')
                    h=held.get((Q,tname,E[addidx[tid]]['_turn'])) if tid in addidx else None
                    # did Q cast anything between the counter's add and its resolve?
                    responded=False
                    if cid in addidx:
                        for x in E[addidx[cid]+1:i]:
                            if x['type']=='STACK_ADD' and x['message'].startswith(Q+' cast'): responded=True; break
                    res[(ag,'held protection' if h else ('no protection in hand' if h is not None else 'hand unknown'),'responded' if responded else 'did not respond')]+=1
    print('==',name)
    for k,v in sorted(res.items()): print('   ',v,k)
