import json, glob, collections, os, re
root = r"C:/Users/Vatto/Magic Rules Engine/studies"
files = glob.glob(root + "/**/*.jsonl", recursive=True)
ev = collections.Counter(); byname = collections.Counter(); perdir = collections.Counter()
events = collections.Counter()
for f in files:
    try:
        fh = open(f, encoding="utf-8", errors="replace")
    except Exception: continue
    d = os.path.relpath(os.path.dirname(f), root)
    for line in fh:
        if '"rec":"agent"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        e = r.get("event"); events[e]+=1
        if e == "combo_cast":
            perdir[d]+=1
            m = re.match(r"(.*) \((\d+)/(\d+) online\)", r.get("detail",""))
            if m: byname[(m.group(1), m.group(2)+"/"+m.group(3))]+=1
print("files", len(files))
print("events", events.most_common(40))
print("combo_cast per dir", perdir.most_common())
for k,v in byname.most_common(40): print(v, k)
