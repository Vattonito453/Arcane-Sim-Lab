import zipfile,re,json,glob,collections,unicodedata
Z=zipfile.ZipFile('C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip')
names=set(Z.namelist())
def fname(card):
    c=card.split(' // ')[0]
    c=unicodedata.normalize('NFKD',c).encode('ascii','ignore').decode()
    c=c.lower().replace("'","").replace(",","").replace(".","").replace("!","").replace("?","")
    c=re.sub(r"[\s\-]+","_",c)
    c=re.sub(r"[^a-z0-9_]","",c)
    return f"{c[0]}/{c}.txt"
cache={}
def flags(card):
    if card in cache: return cache[card]
    f=fname(card)
    if f not in names: cache[card]=None; return None
    t=Z.read(f).decode('utf-8','ignore')
    fl=set()
    if 'AI:RemoveDeck:All' in t: fl.add('RemoveDeck:All')
    if 'AI:RemoveDeck:Random' in t: fl.add('RemoveDeck:Random')
    cache[card]=fl; return fl
if __name__=='__main__':
    tot=0; withall=0; withany=0; missing=set(); bad=collections.Counter(); perdeck=[]
    for f in sorted(glob.glob('C:/Users/Vatto/Magic Rules Engine/studies/behavior_rubric/plans_*.json')):
        d=json.load(open(f,encoding='utf-8'))['decks']
        for deck,p in d.items():
            seen=set(); n=0; na=0
            for l in p.get('lines',[]):
                k=tuple(sorted(l['cards']))
                if k in seen: continue
                seen.add(k); tot+=1; n+=1
                fl=[(c,flags(c)) for c in k]
                for c,x in fl:
                    if x is None: missing.add(c)
                if any(x and 'RemoveDeck:All' in x for c,x in fl):
                    withall+=1; na+=1
                    for c,x in fl:
                        if x and 'RemoveDeck:All' in x: bad[c]+=1
                if any(x for c,x in fl): withany+=1
            perdeck.append((deck,n,na))
    print('unique lines',tot,'with a RemoveDeck:All card',withall,'(%.0f%%)'%(100*withall/tot),'with any RemoveDeck flag',withany,'(%.0f%%)'%(100*withany/tot))
    print('flagged cards:',bad.most_common(25))
    print('script not found for:',sorted(missing)[:20])
    print('decks where EVERY line has a RemoveDeck:All card:',[d for d,n,na in perdeck if n and na==n])
    print('decks where >=half lines flagged:',[(d,na,n) for d,n,na in perdeck if n and na*2>=n])
