import json, glob, os, pickle, re, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__))
info = pickle.load(open(os.path.join(HERE, "cardinfo.pkl"), "rb"))
R = "C:/Users/Vatto/Magic Rules Engine/studies/"

def fl(n):
    n = n.strip()
    c = info.get(n) or info.get(n.split(" // ")[0])
    return c["fl"] if c else "unk"

# 1) precon decks used in precon_predict/runs_stock
decks = set()
for f in glob.glob(R + "precon_predict/runs_stock/*.jsonl"):
    with open(f, encoding="utf-8") as fh:
        r = json.loads(fh.readline())
        for d in r.get("decks", []):
            decks.add(d)
print("precon decks referenced:", len(decks))
per = []
perq = []
cardfreq = collections.Counter()
for d in sorted(decks):
    p = d.replace("\\", "/")
    if not os.path.exists(p):
        print("missing", p); continue
    sec = None; n_all = 0; n_allq = 0
    for line in open(p, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("["):
            sec = line.lower(); continue
        if sec not in ("[main]", "[commander]"):
            continue
        m = re.match(r"(\d+)\s+([^|]+)", line)
        if not m: continue
        q, nm = int(m.group(1)), m.group(2).strip()
        if fl(nm) == "All":
            n_all += 1; n_allq += q; cardfreq[nm] += 1
    per.append(n_all); perq.append(n_allq)
print("precon All-flagged distinct per deck: mean %.2f median %s max %d min %d" % (statistics.mean(per), statistics.median(per), max(per), min(per)))
print("precon All-flagged with qty per deck: mean %.2f" % statistics.mean(perq))
print("most common flagged in precons:", cardfreq.most_common(15))

# 2) plan lines/tutors in cEDH plan files
for pf in sorted(glob.glob(R + "agent_viability/runs_*/plans_*.json") + glob.glob(R + "behavior_rubric/runs_agent_shipping/plans*.json")):
    try:
        P = json.load(open(pf, encoding="utf-8"))
    except Exception as e:
        print("bad", pf, e); continue
    plans = P if isinstance(P, list) else (list(P.values()) if isinstance(P, dict) else [])
    lines = 0; flagged_lines = 0; pieces = 0; fpieces = 0; tut = 0; ftut = 0
    def walk(o):
        if isinstance(o, dict):
            if "lines" in o and isinstance(o["lines"], list):
                yield o
            else:
                for v in o.values():
                    yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    seen = 0
    for pl in walk(P):
        seen += 1
        for ln in pl.get("lines", []):
            names = ln if isinstance(ln, list) else (ln.get("pieces") or ln.get("cards") or [])
            lines += 1
            f_ = [n for n in names if fl(n) == "All"]
            pieces += len(names); fpieces += len(f_)
            if f_: flagged_lines += 1
        for t in pl.get("tutors", []) or []:
            tn = t if isinstance(t, str) else t.get("name", "")
            tut += 1; ftut += fl(tn) == "All"
    print("%s: plans=%d lines=%d withFlagged=%d pieces=%d flaggedPieces=%d tutors=%d flaggedTutors=%d" % (os.path.relpath(pf, R), seen, lines, flagged_lines, pieces, fpieces, tut, ftut))
