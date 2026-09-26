import sys, os, json, glob, collections, re, random, statistics as st
sys.path.insert(0, os.path.dirname(__file__))
from removedeck import read_dck, flag
from detect2 import REPO
sys.path.insert(0, str(REPO / "engine")); import cards
man = json.load(open(REPO / "studies/precon_correlation/manifest.json"))["precons"]
human = {p["forge_file"]: p["human_win_rate"] / 100 for p in man}
share = {}
for p in man:
    f = "C:/Users/Vatto/forge/res/quest/commanderprecons/" + p["forge_file"]
    if not os.path.exists(f): continue
    c = collections.Counter()
    for n, nm in read_dck(f):
        ci = cards.get(nm, fetch=False) or {}
        if "Land" in (ci.get("type_line") or ""): continue
        c[flag(nm)] += n
    s = sum(c.values()); share[p["forge_file"]] = c["All"] / s if s else 0
def simrates(arm):
    w = collections.Counter(); g = collections.Counter()
    for f in glob.glob(str(REPO / f"studies/precon_predict/{arm}/*.jsonl")):
        meta = None
        for line in open(f, encoding="utf-8", errors="replace"):
            if line.startswith('{"rec":"meta"'):
                meta = json.loads(line); decks = [os.path.basename(d) for d in meta["decks"]]; players = meta["players"]
            elif line.startswith('{"rec":"result"'):
                r = json.loads(line)
                if not r.get("winner"): continue
                for p, d in zip(players, decks):
                    g[d] += 1; w[d] += (r["winner"] == p)
    return {d: w[d] / g[d] for d in g if g[d] >= 10}
def corr(x, y):
    mx, my = st.mean(x), st.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return num / ((sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)) ** 0.5)
def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
    for k, i in enumerate(o): r[i] = k
    return r
for arm in ("runs_stock", "runs_agent", "runs_agent_015"):
    sr = simrates(arm)
    ds = [d for d in sr if d in share and d in human]
    x = [share[d] for d in ds]; sim = [sr[d] for d in ds]; hum = [human[d] for d in ds]
    res = [a - b for a, b in zip(sim, hum)]
    c1 = corr(x, res); c2 = corr(x, sim); c3 = corr(x, hum)
    # permutation p for corr(x,res)
    random.seed(1); cnt = 0
    for _ in range(4000):
        xs = x[:]; random.shuffle(xs)
        if abs(corr(xs, res)) >= abs(c1): cnt += 1
    print(f"{arm}: n={len(ds)} decks; mean All-share {st.mean(x):.3f}; corr(All-share, sim-human residual) {c1:+.3f} (perm p={cnt/4000:.3f}); "
          f"corr(All-share, sim) {c2:+.3f}; corr(All-share, human) {c3:+.3f}; spearman(res) {corr(rank(x), rank(res)):+.3f}")
