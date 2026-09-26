import simload, glob, collections, statistics, sys, json
from simload import bare
SETS={'stock_hc':'studies/human_ceiling/runs/*.jsonl','agent093':'studies/behavior_rubric/runs_agent_093/*.jsonl','agentship091':'studies/behavior_rubric/runs_agent_shipping/*.jsonl','av015':'studies/agent_viability/runs_015_default/*.jsonl','av016':'studies/agent_viability/runs_016_engine/*.jsonl'}

def game_lines(G):
    out={}
    for p in G['players']:
        d=bare(p); pl=simload.plans(G['pod']).get(d,{})
        seen=set(); L=[]
        for l in pl.get('lines',[]):
            k=tuple(sorted(l['cards']))
            if k in seen: continue
            seen.add(k); L.append(k)
        out[p]=L
    return out

def analyse(G):
    lines=game_lines(G)
    bf=collections.defaultdict(collections.Counter); hand=collections.defaultdict(collections.Counter)
    cmd=collections.defaultdict(collections.Counter); spelltype={}
    cast_turn=collections.defaultdict(lambda: collections.defaultdict(set))
    first_owned={}; first_asm={}; asm_turns=collections.defaultdict(set)
    for r in G['stream']:
        if r.get('rec')!='zone': continue
        c=r['card']; t=r['turn']; fp=r.get('fromPlayer'); tp=r.get('toPlayer')
        ty=r.get('types') or ''
        if 'Instant' in ty or 'Sorcery' in ty: spelltype[c]=True
        fz,tz=r['from'],r['to']
        if fz=='Battlefield' and fp: bf[fp][c]-=1
        if fz=='Hand' and fp: hand[fp][c]-=1
        if fz=='Command' and fp: cmd[fp][c]-=1
        if tz=='Battlefield' and tp: bf[tp][c]+=1
        if tz=='Hand' and tp: hand[tp][c]+=1
        if tz=='Command' and tp: cmd[tp][c]+=1
        if tz=='Stack' and fz in ('Hand','Command','Graveyard','Exile') and fp: cast_turn[fp][c].add(t)
        for p in (fp,tp):
            if not p or p not in lines: continue
            for L in lines[p]:
                owned=all(bf[p][x]>0 or hand[p][x]>0 or cmd[p][x]>0 or t in cast_turn[p][x] for x in L)
                if owned and (p,L) not in first_owned: first_owned[(p,L)]=t
                asm=all(((spelltype.get(x) and (hand[p][x]>0 or t in cast_turn[p][x])) or bf[p][x]>0) for x in L)
                if asm:
                    asm_turns[(p,L)].add(t)
                    if (p,L) not in first_asm: first_asm[(p,L)]=t
    return lines, first_owned, first_asm, asm_turns

def main(names):
    for name in names:
        rows=[]
        for f in sorted(glob.glob(simload.ROOT+'/'+SETS[name])):
            for G in simload.load(f):
                w=simload.win_info(G); lines,fo,fa,at=analyse(G)
                last=G['last_turn']
                for p in G['players']:
                    if name.startswith('av') and G['agents'].get(p)!='plan': pass
                    own=[t for (q,L),t in fo.items() if q==p]; asm=[t for (q,L),t in fa.items() if q==p]
                    rows.append(dict(pod=G['pod'],deck=bare(p),agent=G['agents'].get(p),file=f,g=G['idx'],
                        nlines=len(lines[p]),owned=min(own) if own else None, asm=min(asm) if asm else None,
                        asm_lines=[L for (q,L) in fa if q==p],
                        won=(w['winner']==p), method=w['method'] if w['winner']==p else None,
                        own_round_asm=simload.player_round(G,p,min(asm)) if asm else None,
                        own_round_owned=simload.player_round(G,p,min(own)) if own else None,
                        end_round=G['own_turns'].get(p), last=last, winner=w['winner'],
                        rounds_after=(simload.round_of(G,last)-simload.round_of(G,min(asm))) if asm else None))
        json.dump(rows, open(f'lines_{name}.json','w'), default=str)
        R=[r for r in rows if r['nlines']>0]
        seats=len(R)
        asmR=[r for r in R if r['asm'] is not None]; ownR=[r for r in R if r['owned'] is not None]
        print(f'== {name}: seats with lines {seats}; owned a full line {len(ownR)}; assembled {len(asmR)}')
        wonA=[r for r in asmR if r['won']]
        print('   assembled & won %d (%.0f%%); of those non-combat wins %d' % (len(wonA), 100*len(wonA)/max(1,len(asmR)), sum(1 for r in wonA if r['method'] and not r['method'].startswith('combat'))))
        if asmR:
            print('   own round at assembly: median %s mean %.1f' % (statistics.median(r['own_round_asm'] for r in asmR), statistics.mean(r['own_round_asm'] for r in asmR)))
            print('   table rounds the game ran AFTER assembly: median %s mean %.1f; zero-lag (ended same round) %d' % (statistics.median(r['rounds_after'] for r in asmR), statistics.mean(r['rounds_after'] for r in asmR), sum(1 for r in asmR if r['rounds_after']==0)))
            lagwon=[r['rounds_after'] for r in wonA]
            if lagwon: print('   winners: rounds between assembly and win: median %s mean %.1f; same-round %d/%d' % (statistics.median(lagwon), statistics.mean(lagwon), sum(1 for x in lagwon if x==0), len(lagwon)))
        c=collections.Counter()
        for r in asmR:
            for L in r['asm_lines']: c[(r['deck'],' + '.join(L))]+=1
        for k,v in c.most_common(25): print('     ',v,k)
if __name__=='__main__': main(sys.argv[1:] or list(SETS))
