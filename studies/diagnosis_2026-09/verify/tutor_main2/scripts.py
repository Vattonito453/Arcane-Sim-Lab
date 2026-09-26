import os,re,json,zipfile
Z=r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip"
CACHE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'scripts_cache.json')
def load():
    if os.path.exists(CACHE): return json.load(open(CACHE,encoding='utf-8'))
    out={}
    with zipfile.ZipFile(Z) as z:
        for n in z.namelist():
            if not n.endswith('.txt'): continue
            txt=z.read(n).decode('utf-8','replace')
            names=re.findall(r'^Name:(.*)$',txt,re.M)
            sp=[l for l in txt.splitlines() if l.startswith('A:SP$')]
            ab=[l for l in txt.splitlines() if l.startswith('A:AB$')]
            for nm in names:
                out.setdefault(nm.strip(),{'sp':sp,'ab':ab,'file':n})
    json.dump(out,open(CACHE,'w',encoding='utf-8'))
    return out
def params(line):
    d={}
    for part in line.split('|'):
        part=part.strip()
        if '$' in part:
            k,v=part.split('$',1); d[k.strip().replace('A:','')]=v.strip()
    return d
def classify(sc):
    for l in sc['sp']:
        p=params(l)
        if p.get('SP')=='ChangeZone' and 'Library' in p.get('Origin','').split(','):
            dest=p.get('Destination','')
            if dest=='Hand': return 'hand'
            if dest=='Library': return 'libtop'
            return 'dest:'+dest
    return None
if __name__=='__main__':
    s=load(); print(len(s))
    for n in ['Demonic Tutor','Vampiric Tutor','Mystical Tutor','Worldly Tutor','Gamble','Intuition','Imperial Seal','Enlightened Tutor','Personal Tutor','Merchant Scroll','Diabolic Intent','Natural Order']:
        print(n, classify(s[n]) if n in s else 'MISSING')
