import json, glob, re, collections, fidx
idx=fidx.load()
S="C:/Users/Vatto/Magic Rules Engine/studies/"
PATS=["agent_viability/runs_015_default/cell_*.jsonl","agent_viability/runs_winmax/cell_*.jsonl","agent_viability/runs_016_engine/cell_*.jsonl","behavior_rubric/runs_agent_shipping/*.jsonl","tutor_targeting/runs_stage2/*.jsonl"]
cc=[]; libself=0
for pat in PATS:
    for f in glob.glob(S+pat):
        for l in open(f,encoding='utf-8'):
            if '"combo_cast"' in l:
                r=json.loads(l); cc.append(re.sub(r" \(\d+/\d+ online\)$","",r['detail']))
            elif '"rec":"zone"' in l and '"from":"Library","to":"Library"' in l: libself+=1
def remall(n):
    e=idx.get(n) or idx.get(n.split(' // ')[0]); return bool(e and re.search(r'^AI:RemoveDeck:All',e['text'],re.M))
print('combo_cast', len(cc), 'RemoveDeck:All pieces', sum(remall(n) for n in cc))
print(collections.Counter(n for n in cc if remall(n)).most_common(12))
print('Library->Library zone records', libself)
d=json.load(open('tc_rows.json')); R=d['rows']
C=collections.Counter
notlib=lambda r: r['loc'] not in ('Library','Library(never moved)')
print('unreachable: type-only mismatch OR not in library:', sum((r['reach'] is False) or notlib(r) for r in R), '/', len(R))
print('unreachable: strict mismatch OR not in library:', sum((r['reach_strict'] is False) or notlib(r) for r in R))
print('not in library:', sum(notlib(r) for r in R), C((r['tutor'],r['want'],r['loc']) for r in R if notlib(r)).most_common(10))
# fetched rate for reachable-and-in-library vs not
ok=[r for r in R if r['reach_strict'] and not notlib(r)]
print('reachable & in library:', len(ok), 'fetched t..t+4', sum(r['fetched'] for r in ok))
bad=[r for r in R if not (r['reach_strict'] and not notlib(r))]
print('unreachable:', len(bad), 'fetched t..t+4', sum(r['fetched'] for r in bad))
# transmute tutors: cast as their spell?
print('transmute tutor_casts', C(r['tutor'] for r in R if r['tutor'] in ('Dizzy Spell','Muddle the Mixture','Drift of Phantasms')), 'went to stack', sum(r['cast'] for r in R if r['tutor'] in ('Dizzy Spell','Muddle the Mixture','Drift of Phantasms')), 'linked search', sum(r['link'] is not None for r in R if r['tutor'] in ('Dizzy Spell','Muddle the Mixture','Drift of Phantasms')))
# linked search offer rate among tutor_casts
L=[r for r in R if r['link']]
print('linked:', len(L), 'comboPick yes', sum(r['link']['comboPick']=='yes' for r in L))
# by dir
bd=collections.defaultdict(lambda: [0,0,0])
for r in R:
    k=r['file'].rsplit('/',1)[0]; bd[k][0]+=1; bd[k][1]+= (r['reach'] is False); bd[k][2]+= r['fetched']
print(dict(bd))
# Godo seat tutor casts
print('godo seat tutor_casts', C((r['tutor'],r['want'],r['reach_strict']) for r in R if 'godo' in r['player']).most_common(12))
print('magda seat tutor_casts', C((r['tutor'],r['want'],r['reach_strict'],r['loc']) for r in R if 'magda' in r['player']).most_common(12))
print('won games among tutor_casts', sum(r['won'] for r in R))
