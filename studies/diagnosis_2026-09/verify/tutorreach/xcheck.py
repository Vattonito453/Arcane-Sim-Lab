"""X-cost tutors: what X did they resolve with, shim-cast vs stock-cast (same files)?
Also: fate of each tutor_cast (resolved / countered / never on stack) from the entry log."""
import json, collections, re, glob
from pathlib import Path
S = Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
XT = {"Chord of Calling", "Green Sun's Zenith", "Nature's Rhythm", "Wargate"}
xs = collections.Counter()
for arm, d in sets.items():
    for fn in sorted(glob.glob(str(S / d / "*.jsonl"))):
        ents = collections.defaultdict(list); agents = collections.defaultdict(list)
        for line in open(fn, encoding="utf-8"):
            if '"rec":"entry"' in line:
                e = json.loads(line); ents[e["game"]].append(e)
            elif '"rec":"agent"' in line and '"tutor_cast"' in line:
                a = json.loads(line); agents[a["game"]].append(a)
        for g, E in ents.items():
            tc = collections.Counter()
            for a in agents.get(g, []):
                tut = a["detail"].split(" seeking ")[0]
                if tut in XT: tc[(a["player"], a["turn"], tut)] += 1
            turn = 0; pending = {}
            for e in E:
                if e["type"] == "TURN":
                    turn = int(re.match(r"Turn (\d+)", e["message"]).group(1))
                if e["type"] == "STACK_ADD" and e.get("card") in XT:
                    m = re.match(r"(Ai\(\d+\)-\S+) cast ", e["message"])
                    if m:
                        who = m.group(1)
                        shim = tc.get((who, turn, e["card"]), 0) > 0
                        if shim: tc[(who, turn, e["card"])] -= 1
                        pending[e["cardId"]] = ("shim" if shim else "stock", e["card"])
                if e["type"] == "STACK_RESOLVE" and e.get("cardId") in pending and "(X=" in e["message"]:
                    who, card = pending.pop(e["cardId"])
                    x = int(re.search(r"\(X=(\d+)\)", e["message"]).group(1))
                    xs[(who, card, "X=0" if x == 0 else "X>0")] += 1
for k, v in sorted(xs.items()): print(v, k)
