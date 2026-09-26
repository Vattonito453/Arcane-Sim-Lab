import json,re,os
S=os.path.dirname(os.path.abspath(__file__))
d=json.load(open(os.path.join(S,'forge_scripts.json'),encoding='utf-8'))
for k in sorted(d):
    t=d[k]; out=[]
    for l in t.splitlines():
        if 'Library' not in l and 'Transmute' not in l and 'Cycling' not in l: continue
        kind = 'SP' if 'SP$' in l else 'AB' if 'AB$' in l else 'TRIG/DB' 
        ct = re.search(r'ChangeType\$ ([^|]*)', l)
        dest = re.search(r'Destination\$ ([^|]*)', l)
        cost = re.search(r'Cost\$ ([^|]*)', l)
        pw = 'Planeswalker$ True' in l
        out.append(f"{kind}{'/PW' if pw else ''} type={ct.group(1).strip() if ct else '?'} dest={dest.group(1).strip() if dest else '?'}{' cost='+cost.group(1).strip() if cost else ''}" if ct or dest else l.strip()[:120])
    print(k,'::',' || '.join(out)[:600])
