"""Fate of each tutor_cast event from the entry log, keyed by the tutor's cardId:
failed-to-target (never on the stack), countered, resolved (with X), or no stack record."""
import json, collections, re, glob
from pathlib import Path
S = Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
rows = json.load(open("reach_rows.json"))
idx = collections.defaultdict(list)
for r in rows: idx[(r["arm"], r["file"], r["game"])].append(r)
fate = collections.Counter(); fate_by = collections.defaultdict(collections.Counter)
for (arm, fn, g), rr in idx.items():
    Z = []; E = []
    for line in open(S / sets[arm] / fn, encoding="utf-8"):
        if f'"game":{g},' not in line: continue
        if '"rec":"zone"' in line: Z.append(json.loads(line))
        elif '"rec":"entry"' in line: E.append(json.loads(line))
    # entry turn map
    turn = 0; ET = []
    for e in E:
        if e["type"] == "TURN": turn = int(re.match(r"Turn (\d+)", e["message"]).group(1))
        ET.append((turn, e))
    used = set()
    for r in rr:
        cids = [z["cardId"] for z in Z if z["card"] == r["tutor"] and z["from"] in ("Hand", "Command")
                and z["to"] == "Stack" and z.get("fromPlayer") == r["player"] and z.get("turn") == r["turn"]]
        f = "no Hand->Stack move"
        for cid in cids:
            evs = [(t, e) for (t, e) in ET if e.get("cardId") == cid and r["turn"] <= t <= r["turn"] + 1
                   and e["type"] in ("STACK_ADD", "STACK_RESOLVE") and (cid, id(e)) not in used]
            evs += [(t, e) for (t, e) in ET if e["type"] == "STACK_ADD" and r["turn"] <= t <= r["turn"] + 1
                    and e["message"].startswith(r["tutor"] + " (" + str(cid) + ") - [Couldn't")]
            adds = [e for t, e in evs if e["type"] == "STACK_ADD"]
            if not adds: continue
            e0 = adds[0]; used.add((cid, id(e0)))
            if "Couldn't add to stack" in e0["message"]:
                f = "failed to put on stack: " + re.search(r"\[Couldn't add to stack, ([^\]]*)\]", e0["message"]).group(1)
            else:
                res = [e for t, e in evs if e["type"] == "STACK_RESOLVE"]
                countered = any(("Counter " + r["tutor"] + " (" + str(cid) + ")") in e["message"] for t, e in ET
                                if r["turn"] <= t <= r["turn"] + 1)
                if countered: f = "countered"
                elif res:
                    m = re.search(r"\(X=(\d+)\)", res[0]["message"])
                    f = "resolved" + (" X=0" if m and m.group(1) == "0" else "")
                else: f = "added, no resolve seen"
            break
        fate[f] += 1; fate_by[f][r["tutor"]] += 1
N = sum(fate.values())
for k, v in fate.most_common():
    print(f"{v:4d} ({100*v/N:4.1f}%) {k}   {fate_by[k].most_common(6)}")
