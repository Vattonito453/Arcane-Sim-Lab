import json, glob, re, collections, os
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
tot = collections.Counter()
for arm, d in ARMS.items():
    agg = collections.Counter()
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        m = POD.search(os.path.basename(f))
        if not m: continue
        pf = (glob.glob(ROOT + d + f"/plans_{m.group(1)}.json") + glob.glob(ROOT + d + f"/plans/plans_{m.group(1)}.json"))[0]
        decks = json.load(open(pf, encoding="utf-8"))["decks"]
        Z = collections.defaultdict(list); S = []
        for line in open(f, encoding="utf-8"):
            if '"rec":"zone"' in line: r = json.loads(line); Z[r["game"]].append(r)
            elif '"search_seen"' in line: S.append(json.loads(line))
        for s in S:
            p = s["player"]; plan = decks.get(p.split("-", 1)[1], {}); L = plan.get("lines", [])
            for mode, cmp in (("lt", lambda t: t < s["turn"]), ("le", lambda t: t <= s["turn"])):
                zone = {}
                for z in Z[s["game"]]:
                    if not cmp(z["turn"]): break
                    zone[z["cardId"]] = (z["to"], z.get("toPlayer"), z["card"])
                B = {nm for (zn, ctl, nm) in zone.values() if zn == "Battlefield" and ctl == p}
                asm = [l for l in L if set(l["cards"]) <= B]
                w = any(WIN.search(" ; ".join(l["produces"])) for l in asm)
                agg[mode + "_post"] += bool(asm); agg[mode + "_nonwinonly"] += bool(asm) and not w
            agg["all"] += 1
    print(f"{arm:12s} searches={agg['all']}  post-assembly: turn<search {agg['lt_post']} ({100*agg['lt_post']/agg['all']:.0f}%, nonwin-only {agg['lt_nonwinonly']})  turn<=search {agg['le_post']} ({100*agg['le_post']/agg['all']:.0f}%, nonwin-only {agg['le_nonwinonly']})")
    if arm != "rubric_ship": tot.update(agg)
print("av arms pooled:", dict(tot))
