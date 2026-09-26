import zipfile, json, collections, re
S='C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad/diagnosis/'
z=zipfile.ZipFile('C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip')
flags={}
for n in z.namelist():
    if not n.endswith('.txt'): continue
    t=z.read(n).decode('utf-8','replace')
    names=re.findall(r'^Name:(.*)$', t, re.M)
    fl=set()
    if re.search(r'^AI:RemoveDeck:All', t, re.M): fl.add('RemoveDeckAll')
    if 'AILogic$ Never' in t: fl.add('AILogicNever')
    if re.search(r'^AI:RemoveDeck:Random', t, re.M): fl.add('RemoveDeckRandom')
    for nm in names: flags[nm.strip()]=fl
lines=json.load(open(S+'verify/combo_loops/lines.json'))
cnt=0; pc=collections.Counter(); unk=set(); never=0
for l in lines:
    hit=False; hitn=False
    for c in l['cards']:
        parts=[c]+c.split(' // ')
        f=None
        for p in parts:
            if p in flags: f=flags[p]; break
        if f is None: unk.add(c); continue
        if 'RemoveDeckAll' in f: hit=True; pc[c]+=1
        if 'AILogicNever' in f: hitn=True
    cnt+=hit; never+=hitn
print('lines with a RemoveDeck:All piece', cnt, 'of', len(lines))
print('lines with an AILogic$ Never piece', never)
print(pc.most_common(20))
print('unknown names', unk)
