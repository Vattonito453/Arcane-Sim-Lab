import zipfile, json, sys, os
S=os.path.dirname(os.path.abspath(__file__))
tutors=[l.strip() for l in open(os.path.join(S,'tutors.txt'),encoding='utf-8') if l.strip()]
z=zipfile.ZipFile(r'C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip')
want=set(tutors); out={}
for n in z.namelist():
    if not n.endswith('.txt'): continue
    t=z.read(n).decode('utf-8','replace')
    for line in t.splitlines():
        if line.startswith('Name:'):
            nm=line[5:].strip()
            if nm in want: out[nm]=t
            break
json.dump(out,open(os.path.join(S,'forge_scripts.json'),'w',encoding='utf-8'),indent=1)
print(len(out),'of',len(want)); print(sorted(want-set(out)))
