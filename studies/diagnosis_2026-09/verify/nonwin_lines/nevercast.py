import json, glob, re, collections, os
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
tally = collections.defaultdict(lambda: [0, 0])  # card -> [fetched to hand/top, never used]
tallyall = collections.defaultdict(lambda: [0, 0])
for arm, d in ARMS.items():
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        if not POD.search(os.path.basename(f)): continue
        seen = {}; steer = {}; zones = collections.defaultdict(list)
        for line in open(f, encoding="utf-8"):
            if '"rec":"zone"' in line:
                r = json.loads(line); zones[r["game"]].append(r); continue
            if '"search_seen"' in line or '"tutor_steer"' in line:
                r = json.loads(line)
                sid = re.search(r"sid=(\d+)", r["detail"]).group(1)
                (seen if r["event"] == "search_seen" else steer)[(r["game"], r["player"], sid)] = r
        for key, s in seen.items():
            g, p, sid = key
            st = steer.get(key)
            dest = re.search(r"dest=(\w+)", s["detail"]).group(1)
            if dest not in ("Hand", "Library"): continue
            if st: card = re.search(r"steer=(.+?) over=", st["detail"]).group(1)
            else:
                m = re.search(r"picked=(.+?) planPick=", s["detail"]); card = m.group(1) if m else None
            if not card or card == "-": continue
            used = any(z["card"] == card and z["turn"] >= s["turn"] and z["to"] in ("Stack", "Battlefield") and z["from"] in ("Hand", "Library") and (z.get("toPlayer") == p or z.get("fromPlayer") == p) for z in zones[g])
            for T in ([tally] if st else []) + [tallyall]:
                T[card][0] += 1; T[card][1] += (not used)
for name, T in (("steered only", tally), ("all plan+stock fetches by any seat to hand/top", tallyall)):
    print(name)
    for c in ["Copy Enchantment", "Devoted Druid", "Chromatic Orrery", "Metalworker"]:
        print(f"   {c:20s} fetched={T[c][0]:3d} never cast/entered={T[c][1]:3d}")
    n = sum(v[0] for v in T.values()); u = sum(v[1] for v in T.values())
    print(f"   overall fetched={n} never used={u} ({100*u/max(n,1):.0f}%)")
