import simload, glob, collections, statistics, sys, json
from lines import SETS, game_lines
from simload import bare
GENERIC={"Demonic Tutor","Vampiric Tutor","Imperial Seal","Mystical Tutor","Worldly Tutor","Enlightened Tutor","Grim Tutor","Diabolic Intent","Gamble","Chord of Calling","Eldritch Evolution","Green Sun's Zenith","Finale of Devastation","Natural Order","Beseech the Mirror","Wishclaw Talisman","Summoner's Pact","Nature's Rhythm","Crop Rotation","Transmute Artifact","Muddle the Mixture","Intuition","Gifts Ungiven","Idyllic Tutor","Personal Tutor","Tainted Pact","Birthing Pod","Neoform","Shared Summons","Wargate","Tooth and Nail","Survival of the Fittest","Invasion of Ikoria","Fabricate","Reckless Handling","Expedition Map","Scheming Symmetry","Spellseeker","Trinket Mage","Recruiter of the Guard","Ranger-Captain of Eos","Moggcatcher","Goblin Matron","Stoneforge Mystic","Merchant Scroll","Solve the Equation","Mastermind's Acquisition","Dark Petition","Profane Tutor","Sidisi's Faithful","Transmutation Font","Lim-Dul's Vault","Inventors' Fair","Whir of Invention","Trophy Mage","Tribute Mage","Kuldotha Forgemaster","Goblin Engineer","Imperial Recruiter","Fierce Empath","Woodland Bellower","Tezzeret the Seeker","Tezzeret, Cruel Captain"}
ENGINE={"Rhystic Study","Mystic Remora","Necropotence","Esper Sentinel","Smothering Tithe","Seedborn Muse","The One Ring","Sylvan Library","Bolas's Citadel","Ad Nauseam","Peer into the Abyss","Consecrated Sphinx","Timetwister","Wheel of Fortune","Windfall","Jeska's Will","Dockside Extortionist","Faerie Mastermind","Tymna the Weaver","Thrasios, Triton Hero"}
INTERACT_ROLES={"protection","removal"}
def cls(card, pl, lines):
    roles=pl.get('roles',{}); r=roles.get(card,'?')
    inline=any(card in L for L in lines)
    if inline or r in('combo-piece','payoff'): return 'combo/payoff'
    if card in ENGINE: return 'engine/draw'
    if r in INTERACT_ROLES: return 'interaction'
    if r=='enabler': return 'ramp'
    if r=='tutor': return 'tutor'
    if r=='land': return 'land'
    if r=='commander': return 'commander'
    return 'other:'+r
def run(name):
    rows=[]
    for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
        for G in simload.load(f):
            w=simload.win_info(G); lines=game_lines(G)
            bf=collections.defaultdict(collections.Counter); hand=collections.defaultdict(collections.Counter); cmd=collections.defaultdict(collections.Counter)
            Z=[r for r in G['stream'] if r.get('rec')=='zone']
            for i,r in enumerate(Z):
                c=r['card']; fp=r.get('fromPlayer'); tp=r.get('toPlayer'); fz,tz=r['from'],r['to']; t=r['turn']
                # detect tutor cast BEFORE applying
                if tz=='Stack' and fz=='Hand' and fp:
                    pl=simload.plans(G['pod']).get(bare(fp),{})
                    tut=set(pl.get('tutors',[]))|GENERIC
                    if c in tut:
                        def missing():
                            best=None
                            for L in lines[fp]:
                                m=sum(1 for x in L if not(bf[fp][x]>0 or hand[fp][x]>0 or cmd[fp][x]>0))
                                best=m if best is None else min(best,m)
                            return best
                        miss_before=missing()
                        fetched=None
                        for x in Z[i+1:i+12]:
                            if x['from']=='Library' and x.get('fromPlayer')==fp and x['to'] in('Hand','Battlefield','Library','Graveyard'):
                                fetched=x['card']; break
                            if x['card']==c and x['from']=='Stack': 
                                # allow one more look after resolution
                                pass
                        active=G['turn_player'].get(t)
                        rows.append(dict(set=name,pod=G['pod'],deck=bare(fp),agent=G['agents'].get(fp),tutor=c,fetched=fetched,
                            cls=cls(fetched,pl,lines[fp]) if fetched else 'none',round=simload.player_round(G,fp,t),
                            own_turn=(active==fp), miss_before=miss_before,
                            won=(w['winner']==fp), win_round=w['win_round'] if w['winner']==fp else None,
                            game=(f,G['idx']), turn=t))
                if fz=='Battlefield' and fp: bf[fp][c]-=1
                if fz=='Hand' and fp: hand[fp][c]-=1
                if fz=='Command' and fp: cmd[fp][c]-=1
                if tz=='Battlefield' and tp: bf[tp][c]+=1
                if tz=='Hand' and tp: hand[tp][c]+=1
                if tz=='Command' and tp: cmd[tp][c]+=1
    return rows
def summarize(rows,label):
    if not rows: print(label,'none'); return
    n=len(rows)
    print(f'== {label}: tutor casts {n}')
    rs=[r['round'] for r in rows]
    print('   round: mean %.1f median %s; share cast in rounds 1-3: %.0f%%; off own turn (instant-speed on opp turn): %.0f%%'%(statistics.mean(rs),statistics.median(rs),100*sum(x<=3 for x in rs)/n,100*sum(not r['own_turn'] for r in rows)/n))
    c=collections.Counter(r['cls'].split(':')[0] for r in rows)
    print('   fetched class:',{k:'%d (%.0f%%)'%(v,100*v/n) for k,v in c.most_common()})
    mb=collections.Counter(r['miss_before'] for r in rows)
    print('   nearest line missing pieces at cast time:',dict(sorted(mb.items(), key=lambda x:(x[0] is None, x[0] or 0))))
if __name__=='__main__':
    allrows=[]
    for name in sys.argv[1:]:
        rows=run(name); allrows+=rows
        for ag in ('stock','plan'):
            summarize([r for r in rows if r['agent']==ag], f'{name}/{ag}')
    json.dump(allrows,open('tutor_rows.json','w'),default=str)
