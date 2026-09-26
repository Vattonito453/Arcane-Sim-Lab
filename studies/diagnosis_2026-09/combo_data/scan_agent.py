import json, glob, re, collections, sys
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
files = glob.glob(R + "/**/*.jsonl", recursive=True)
ev = collections.Counter(); bycard = collections.defaultdict(collections.Counter)
shims = collections.Counter()
example = {}
for f in files:
    shim = None
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"rec":"meta"' in line[:20]:
                try: shim = json.loads(line).get("shim")
                except: pass
                continue
            if '"rec":"agent"' not in line[:20]: continue
            try: r = json.loads(line)
            except: continue
            e = r.get("event"); d = r.get("detail", "")
            ev[e] += 1
            if e and (e.startswith("combo") or e.startswith("tutor")):
                card = re.split(r" \(| seeking | vs | kept ", d)[0]
                bycard[e][card] += 1
                example.setdefault(e, (f, r))
    shims[shim] += 1
print("files", len(files), "shim versions", shims.most_common())
for k, v in ev.most_common(60): print(v, k)
for e in bycard:
    print("==", e, sum(bycard[e].values()))
    for c, n in bycard[e].most_common(25): print("   ", n, c)
for e, (f, r) in example.items(): print(e, f.split("studies")[1], r)
