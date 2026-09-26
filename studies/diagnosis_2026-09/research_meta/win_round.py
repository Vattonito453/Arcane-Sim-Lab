# Win round = number of turns the WINNER has taken (the human-trace unit), per winning pilot.
import os, json, glob, re, collections, sys, statistics
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
TURN = re.compile(r"^Turn (\d+) \((Ai\(\d\)-.+)\)$")
for d in sys.argv[1:]:
    wr = collections.defaultdict(list)
    for p in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
        agents = {}; own = collections.defaultdict(collections.Counter); results = {}
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"rec":"meta"'):
                    m = json.loads(line); agents = dict(zip(m["players"], m.get("agents") or ["stock"]*4))
                elif line.startswith('{"rec":"entry"') and '"type":"TURN"' in line:
                    e = json.loads(line); mm = TURN.match(e["message"])
                    if mm: own[e["game"]][mm.group(2)] += 1
                elif line.startswith('{"rec":"result"'):
                    r = json.loads(line); results[r["game"]] = r
        for g, r in results.items():
            w = r.get("winner")
            if w and not r.get("timedOut"): wr[agents.get(w, "stock")].append(own[g][w])
    out = []
    for pil, v in sorted(wr.items()):
        v.sort()
        out.append(f"{pil}: n={len(v)} mean={statistics.mean(v):.1f} median={statistics.median(v)} <=6: {sum(1 for x in v if x<=6)} ({100*sum(1 for x in v if x<=6)/len(v):.0f}%)")
    print(f"{d:42s}", " | ".join(out))
