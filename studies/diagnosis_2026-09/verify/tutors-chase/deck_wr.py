import json, glob, collections
from pathlib import Path
R = "C:/Users/Vatto/Magic Rules Engine/studies/agent_viability"
S = collections.defaultdict(collections.Counter)
for f in sorted(glob.glob(R + "/runs_*/*.jsonl")):
    fh = open(f, encoding="utf-8", errors="replace")
    meta = json.loads(fh.readline())
    if meta.get("rec") != "meta": continue
    ag = {p: meta["agents"][i] for i, p in enumerate(meta["players"])}
    dk = {p: Path(d.replace("\\","/")).stem for p, d in zip(meta["players"], meta["decks"])}
    for line in fh:
        if '"rec":"result"' not in line: continue
        r = json.loads(line)
        for p in meta["players"]:
            S[(dk[p], ag[p])]["g"] += 1; S[(dk[p], ag[p])]["w"] += r.get("winner") == p
for d in sorted({k[0] for k in S}):
    a, b = S[(d, "plan")], S[(d, "stock")]
    print(f"{d:20s} plan {a['w']}/{a['g']} ({100*a['w']/max(1,a['g']):.0f}%)  stock {b['w']}/{b['g']} ({100*b['w']/max(1,b['g']):.0f}%)")
