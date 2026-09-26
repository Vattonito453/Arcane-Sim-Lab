import json, glob, collections, re
from classify import cls
def strip(p): return re.sub(r"^Ai\(\d+\)-", "", p or "")
base = "C:/Users/Vatto/Magic Rules Engine/studies/"
for runs, plans_dir in [("behavior_rubric/runs_agent_shipping", "behavior_rubric/runs_agent_shipping/plans"),
                        ("agent_viability/runs_015_default", "agent_viability/runs_015_default"),
                        ("agent_viability/runs_winmax", "agent_viability/runs_winmax"),
                        ("agent_viability/runs_016_engine", "agent_viability/runs_016_engine")]:
    plans = {}
    for f in glob.glob(base + plans_dir + "/plans_*.json"):
        for name, plan in json.load(open(f, encoding="utf-8"))["decks"].items():
            plans[name] = [(set(ln["cards"]), cls(ln.get("produces", []), "lenient")) for ln in plan["lines"]]
    c = collections.Counter(); samples = collections.defaultdict(list)
    for f in glob.glob(base + runs + "/*.jsonl"):
        for l in open(f, encoding="utf-8"):
            if '"agent"' not in l: continue
            r = json.loads(l)
            ev = r.get("event")
            if ev not in ("combo_cast", "tutor_steer", "tutor_cast"): continue
            d = r.get("detail", "")
            deck = strip(r.get("player"))
            lines = plans.get(deck, [])
            # candidate card names: any line card mentioned in detail
            hit = {k for ln, k in lines for card in ln if card in d}
            kind = "win" if "win" in hit else ("resource" if hit else "no-line-card")
            c[(ev, kind)] += 1
            if len(samples[(ev, kind)]) < 2: samples[(ev, kind)].append((deck, d))
    print(runs)
    for k in sorted(c): print("   ", k, c[k], samples[k][:1])
