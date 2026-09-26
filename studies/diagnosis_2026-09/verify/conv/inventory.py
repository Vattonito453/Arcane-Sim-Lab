import json, glob, collections
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
by_dir = collections.Counter(); shims=collections.Counter(); agents=collections.Counter()
files=[]
for f in glob.glob(R + "/**/*.jsonl", recursive=True):
    with open(f, encoding="utf-8", errors="replace") as fh:
        try: meta = json.loads(fh.readline())
        except Exception: continue
    if meta.get("rec") != "meta" or not meta.get("decks"): continue
    if not any("human_ceiling" in d for d in meta["decks"]): continue
    d = f.replace("\\","/").split("/studies/")[1].rsplit("/",1)[0]
    by_dir[d]+=1; shims[meta.get("shim")]+=1
    agents[tuple(meta.get("agents") or ["?"])]+=1
    files.append(f)
print(len(files))
for k,v in sorted(by_dir.items()): print(v,k)
print(shims); print(agents)
json.dump(files, open("files.json","w"))
