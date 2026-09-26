import zipfile, re, json, glob, collections, os
z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
info = {}
for n in z.namelist():
    if not n.endswith('.txt'): continue
    t = z.read(n).decode('utf-8','replace')
    fl = 'All' in re.findall(r'^AI:RemoveDeck:(\w+)', t, re.M)
    names = re.findall(r'^Name:(.*)$', t, re.M); types = re.findall(r'^Types:(.*)$', t, re.M)
    if names:
        info[names[0].strip()] = (fl, 'Land' in (types[0].split() if types else []))
        for nm in names[1:]: info.setdefault(nm.strip(), (fl, 'Land' in (types[0].split() if types else [])))
def read(p):
    sec=None; out=[]
    for line in open(p, encoding='utf-8', errors='replace'):
        line=line.strip()
        if line.startswith('['): sec=line.lower(); continue
        m = re.match(r'^(\d+)\s+(.+?)(?:\|.*)?$', line)
        if m and sec in ('[main]','[commander]'): out.append((int(m.group(1)), m.group(2).strip()))
    return out
def report(label, files):
    tot = collections.Counter(); per=[]; unknown=collections.Counter()
    for f in files:
        c = collections.Counter()
        for n,nm in read(f):
            k = info.get(nm) or (info.get(nm.split(' // ')[0]) if ' // ' in nm else None)
            if k is None: unknown[nm]+=n; continue
            if k[1]: continue
            c['non']+=n; c['all']+=n*k[0]
        tot.update(c); per.append((c['all']/max(1,c['non']), os.path.basename(f)))
    per.sort(reverse=True)
    print(label, len(files), 'decks', f"{tot['all']}/{tot['non']} = {tot['all']/tot['non']:.3f}", 'median', round(sorted(p[0] for p in per)[len(per)//2],3), 'worst', [(round(a,3),b) for a,b in per[:3]], 'unknown names', sum(unknown.values()))
R = r"C:/Users/Vatto/Magic Rules Engine/studies/"
report('cEDH', glob.glob(R+'human_ceiling/decks/*/dck/*.dck'))
metas=set()
for f in glob.glob(R+'precon_predict/runs_agent_015/*.jsonl'):
    metas |= set(json.loads(open(f,encoding='utf-8').readline()).get('decks',[]))
print(len(metas), list(metas)[:2])
report('precon', [m for m in metas if os.path.exists(m)])
