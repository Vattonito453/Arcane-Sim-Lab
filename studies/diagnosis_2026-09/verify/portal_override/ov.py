import json, glob, os, re, sys, collections
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
ARMS = {
 'av015': ROOT+'/agent_viability/runs_015_default',
 'winmax': ROOT+'/agent_viability/runs_winmax',
 'av016': ROOT+'/agent_viability/runs_016_engine',
 'nocombo': ROOT+'/agent_viability/runs_nocombo',
 'pilot': ROOT+'/agent_viability/runs_pilot',
}
if len(sys.argv) > 1:
    ARMS = {k: v for k, v in ARMS.items() if k in sys.argv[1:]}
def kv(detail):
    # parse single-token fields before names; names start at ' missing='
    d = {}
    m = re.match(r'(.*?) missing=(.*) picked=(.*) planPick=(.*) src=(.*)$', detail)
    if m:
        head, d['missing'], d['picked'], d['planPick'], d['src'] = m.groups()
    else:
        head = detail
    for tok in head.split():
        if '=' in tok:
            k, v = tok.split('=', 1); d[k] = v
    return d
def steerkv(detail):
    m = re.match(r'sid=(\d+) mode=(\S+) value=(\d+) stockValue=(\d+) steer=(.*) over=(.*)$', detail)
    return dict(zip(['sid','mode','value','stockValue','steer','over'], m.groups())) if m else None
for arm, d in ARMS.items():
    seen = {}; steers = {}
    for f in sorted(glob.glob(d+'/cell_*.jsonl')):
        for l in open(f, encoding='utf-8'):
            r = json.loads(l)
            if r['rec'] != 'agent': continue
            if r['event'] == 'search_seen':
                x = kv(r['detail'])
                seen[(f, r['game'], r['player'], x['sid'])] = (x, r)
            elif r['event'] == 'tutor_steer':
                x = steerkv(r['detail'])
                steers[(f, r['game'], r['player'], x['sid'])] = x
    portal = [(k, v) for k, v in seen.items() if 'Portal to Phyrexia' in v[0].get('picked', '').split('|')]
    ov = [(k, v) for k, v in portal if k in steers]
    repl = collections.Counter(steers[k]['steer'] for k, v in ov)
    modes = collections.Counter(steers[k]['mode'] for k, v in ov)
    srcs = collections.Counter(v[0].get('src') for k, v in portal)
    players = collections.Counter(k[2].split('-',1)[1] for k,v in portal)
    print(f"{arm}: search_seen={len(seen)} steers={len(steers)} portal_picked={len(portal)} overridden={len(ov)} modes={dict(modes)} players={dict(players)}")
    print("   replacements:", dict(repl.most_common()))
    print("   srcs:", dict(srcs))
    # not overridden ones
    for k, v in portal:
        if k not in steers:
            print("   NOT overridden:", v[1]['detail'][:250])
