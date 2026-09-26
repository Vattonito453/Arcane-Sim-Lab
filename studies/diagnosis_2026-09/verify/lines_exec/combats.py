import glob, json, re, collections, os
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
TURN = re.compile(r"^Turn (\d+) \((.+)\)$")
cnt = collections.defaultdict(list)
for f in glob.glob(ROOT + "/**/*.jsonl", recursive=True):
    with open(f, encoding="utf-8") as fh:
        first = fh.readline()
        if "human_ceiling" not in first:
            continue
        meta = json.loads(first)
        ag = dict(zip(meta.get("players") or [], meta.get("agents") or []))
        cur = {}; da = collections.Counter(); win = {}
        for l in fh:
            if '"PHASE"' not in l and '"TURN"' not in l and '"result"' not in l:
                continue
            r = json.loads(l)
            g = r.get("game")
            if r.get("rec") == "result":
                win[g] = (r.get("winner"), r.get("turns")); continue
            m = r.get("message", "")
            if r.get("type") == "TURN":
                mm = TURN.match(m)
                if mm: cur[g] = (int(mm.group(1)), mm.group(2))
            elif "Declare Attackers Step" in m and g in cur:
                da[(g,) + cur[g]] += 1
    for (g, t, p), n in da.items():
        w = win.get(g, (None, None))
        deck = p.split("-", 1)[1]
        cnt[deck].append((n, ag.get(p), w[0] == p and w[1] == t, os.path.relpath(f, ROOT), g, t))
for deck, xs in sorted(cnt.items(), key=lambda kv: -max(x[0] for x in kv[1])):
    big = [x for x in xs if x[0] >= 3]
    if not big: continue
    print(f"{deck:22s} max combats/turn {max(x[0] for x in xs):3d}; turns with >=3 combats {len(big)}; of those same-turn wins {sum(x[2] for x in big)}; agents {dict(collections.Counter(x[1] for x in big))}")
