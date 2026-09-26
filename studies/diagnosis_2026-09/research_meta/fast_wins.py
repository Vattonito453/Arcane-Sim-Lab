import os, json, glob, re, collections, sys
from math import comb
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
TURN = re.compile(r"^Turn (\d+) \((Ai\(\d\)-.+)\)$")
SPELL = re.compile(r"won by spell '([^']+)'")
def fisher_greater(a, b, c, d):
    # P(X >= a) for 2x2 [[a,b],[c,d]] one-sided
    n1, n2, k = a + b, c + d, a + c; N = n1 + n2
    return sum(comb(n1, x) * comb(n2, k - x) for x in range(a, min(n1, k) + 1)) / comb(N, k)
agg = collections.Counter(); detail = collections.Counter()
for d in sys.argv[1:]:
    for p in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
        agents = {}; own = collections.defaultdict(collections.Counter); res = {}; spell = {}
        for line in open(p, encoding="utf-8", errors="replace"):
            if line.startswith('{"rec":"meta"'):
                m = json.loads(line); agents = dict(zip(m["players"], m.get("agents") or ["stock"]*4))
            elif '"type":"TURN"' in line:
                e = json.loads(line); mm = TURN.match(e["message"])
                if mm: own[e["game"]][mm.group(2)] += 1
            elif '"type":"GAME_OUTCOME"' in line and "won by spell" in line:
                e = json.loads(line); spell[e["game"]] = SPELL.search(e["message"]).group(1)
            elif line.startswith('{"rec":"result"'):
                r = json.loads(line); res[r["game"]] = r
        arm = d.split("/")[-1]
        for g, r in res.items():
            w = r.get("winner")
            if not w or r.get("timedOut"): continue
            pil = agents.get(w, "stock"); rnd = own[g][w]
            agg[(arm, pil, "wins")] += 1
            if rnd <= 6:
                agg[(arm, pil, "fast")] += 1
                detail[(arm, pil, re.sub(r"^Ai\(\d\)-", "", w), spell.get(g, "no spell-win line"))] += 1
for arm in sorted({k[0] for k in agg}):
    print(arm, {pil: f"{agg[(arm,pil,'fast')]}/{agg[(arm,pil,'wins')]}" for pil in ("plan","stock")})
on = [a for a in {k[0] for k in agg} if a != "runs_nocombo"]
pf = sum(agg[(a,"plan","fast")] for a in on); pw = sum(agg[(a,"plan","wins")] for a in on)
sf = sum(agg[(a,"stock","fast")] for a in on); sw = sum(agg[(a,"stock","wins")] for a in on)
nf, nw = agg[("runs_nocombo","plan","fast")], agg[("runs_nocombo","plan","wins")]
print(f"combo-on plan fast {pf}/{pw}; stock (same games) {sf}/{sw}; nocombo plan {nf}/{nw}")
print("Fisher one-sided plan(on) vs stock:", fisher_greater(pf, pw-pf, sf, sw-sf))
print("Fisher one-sided plan(on) vs plan(nocombo):", fisher_greater(pf, pw-pf, nf, nw-nf))
for k, v in detail.most_common(): print("  ", v, k)
