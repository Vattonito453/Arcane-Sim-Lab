import json, glob, re, collections, os, sys
sys.path.insert(0, ".")
from lenient import classify, load, ORDER, WIN
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
def rnd(turn, n): return None if turn is None else (turn - 1) // n + 1
strict = collections.defaultdict(collections.Counter); len_ = collections.defaultdict(collections.Counter)
steered_only = collections.defaultdict(collections.Counter)
for arm, d in ARMS.items():
    PP = load(ROOT + d + "/plans_*.json") or load(ROOT + d + "/plans/plans_*.json")
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        m = POD.search(os.path.basename(f))
        if not m: continue
        decks = PP[m.group(1)]
        meta = None; seen = {}; steer = {}; res = {}
        for line in open(f, encoding="utf-8"):
            if '"rec":"entry"' in line or '"rec":"tap"' in line or '"rec":"zone"' in line: continue
            try: r = json.loads(line)
            except: continue
            rc = r.get("rec")
            if rc == "meta": meta = r
            elif rc == "result": res[r["game"]] = r
            elif rc == "agent" and r["event"] in ("search_seen", "tutor_steer"):
                sid = re.search(r"sid=(\d+)", r["detail"]).group(1)
                key = (r["game"], r["player"], sid)
                (seen if r["event"] == "search_seen" else steer)[key] = r
        nseat = len(meta["players"])
        for key, s in seen.items():
            g, p, sid = key
            deck = p.split("-", 1)[1]; plan = decks.get(deck, {}); cards = set(plan.get("roles", {}).keys())
            st = steer.get(key)
            if st: taken = re.search(r"steer=(.+?) over=", st["detail"]).group(1)
            else:
                mm = re.search(r"picked=(.+?) planPick=", s["detail"]); taken = mm.group(1) if mm else None
            if not taken or taken == "-": continue
            L = [l for l in plan.get("lines", []) if taken in l["cards"]]
            sc = "win" if any(WIN.search(" ; ".join(l["produces"])) for l in L) else ("nonwin" if L else "notline")
            lc = min((classify(l, cards) for l in L), key=ORDER.index) if L else "notline"
            R = res.get(g)
            if not R: continue
            won = R.get("winner") == p
            soon = won and rnd(R["turns"], nseat) - rnd(s["turn"], nseat) <= 2
            for tab, c in ((strict, sc), (len_, lc)):
                tab[c]["n"] += 1; tab[c]["won"] += won; tab[c]["soon"] += soon
            if st:
                steered_only[sc]["n"] += 1; steered_only[sc]["won"] += won; steered_only[sc]["soon"] += soon
def show(name, tab):
    print(name)
    for c, v in sorted(tab.items(), key=lambda kv: -kv[1]["n"]):
        print(f"   {c:30s} n={v['n']:4d} seat won={100*v['won']/v['n']:.0f}%  won<=2 rounds after={100*v['soon']/v['n']:.0f}% ({v['soon']})")
show("plan-seat searches, strict classes (pooled 4 arms)", strict)
show("plan-seat searches, lenient classes", len_)
show("steered searches only, strict", steered_only)
