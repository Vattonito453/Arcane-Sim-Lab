"""For tutor casts with no search_seen: what did the log say happened to the tutor?"""
import json, collections, re
from pathlib import Path
S = Path(r"C:/Users/Vatto/Magic Rules Engine/studies")
sets = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
rows = json.load(open("reach_rows.json"))
want = [r for r in rows if r["combo"] is None and r["actual"]]
byfile = collections.defaultdict(list)
for r in want: byfile[(r["arm"], r["file"])].append(r)
res = collections.Counter(); ex = collections.defaultdict(list)
for (arm, fn), rr in byfile.items():
    ents = collections.defaultdict(list); agents = collections.defaultdict(list)
    for line in open(S / sets[arm] / fn, encoding="utf-8"):
        if '"rec":"entry"' in line:
            e = json.loads(line); ents[e["game"]].append(e)
        elif '"rec":"agent"' in line:
            a = json.loads(line); agents[a["game"]].append(a)
    for r in rr:
        E = ents[r["game"]]; turn = 0; state = None; cid = None; txt = None
        for e in E:
            if e["type"] == "TURN":
                m = re.match(r"Turn (\d+)", e["message"]); turn = int(m.group(1))
                if turn > r["turn"] + 1: break
            if turn < r["turn"]: continue
            if cid is None and e["type"] == "STACK_ADD" and e.get("card") == r["tutor"] and e["message"].startswith(r["player"] + " cast"):
                cid = e.get("cardId"); state = "cast"; txt = e["message"]
                continue
            if cid is not None and e.get("cardId") == cid and e["type"] == "STACK_RESOLVE":
                state = "resolved"; txt = e["message"]; break
            if cid is not None and ("countered" in e["message"].lower()) and r["tutor"] in e["message"]:
                state = "countered"; txt = e["message"]; break
        # any later search_seen with this src at all in game?
        later = [a for a in agents[r["game"]] if a["event"] == "search_seen" and a["player"] == r["player"]
                 and a["detail"].endswith("src=" + r["tutor"]) and a["turn"] > r["turn"] + 1]
        skipped = [a for a in agents[r["game"]] if a["event"] == "search_skipped" and a["player"] == r["player"]
                   and r["tutor"] in a["detail"] and r["turn"] <= a["turn"] <= r["turn"] + 1]
        k = (r["kind"], state, "laterSearch" if later else "", "skipped" if skipped else "")
        res[k] += 1
        if len(ex[k]) < 4: ex[k].append((r["tutor"], r["want"], r["file"], r["game"], r["turn"], (txt or "")[:170]))
for k, v in res.most_common():
    print(v, k)
    for x in ex[k]: print("     ", x)
