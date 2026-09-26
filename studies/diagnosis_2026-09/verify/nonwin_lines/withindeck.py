import json, glob, re, collections, os
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
T = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
for arm, d in ARMS.items():
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        m = POD.search(os.path.basename(f))
        if not m: continue
        pf = (glob.glob(ROOT + d + f"/plans_{m.group(1)}.json") + glob.glob(ROOT + d + f"/plans/plans_{m.group(1)}.json"))[0]
        decks = json.load(open(pf, encoding="utf-8"))["decks"]
        meta = None; seen = {}; steer = {}; R = {}
        for line in open(f, encoding="utf-8"):
            if '"rec":"meta"' in line: meta = json.loads(line)
            elif '"rec":"result"' in line: r = json.loads(line); R[r["game"]] = r
            elif '"search_seen"' in line or '"tutor_steer"' in line:
                r = json.loads(line); sid = re.search(r"sid=(\d+)", r["detail"]).group(1)
                (seen if r["event"] == "search_seen" else steer)[(r["game"], r["player"], sid)] = r
        n = len(meta["players"])
        for key, s in seen.items():
            g, p, sid = key; deck = p.split("-", 1)[1]; plan = decks.get(deck, {})
            st = steer.get(key)
            if st: taken = re.search(r"steer=(.+?) over=", st["detail"]).group(1)
            else:
                mm = re.search(r"picked=(.+?) planPick=", s["detail"]); taken = mm.group(1) if mm else None
            if not taken or taken == "-" or g not in R: continue
            L = [l for l in plan.get("lines", []) if taken in l["cards"]]
            if not L: continue
            c = "win" if any(WIN.search(" ; ".join(l["produces"])) for l in L) else "nonwin"
            won = R[g].get("winner") == p
            soon = won and ((R[g]["turns"] - 1)//n + 1) - ((s["turn"] - 1)//n + 1) <= 2
            T[deck][c]["n"] += 1; T[deck][c]["soon"] += soon; T[deck][c]["won"] += won
num = den = 0; W = collections.Counter()
for deck, cc in sorted(T.items()):
    if cc["win"]["n"] >= 3 and cc["nonwin"]["n"] >= 3:
        a = cc["win"]; b = cc["nonwin"]
        print(f"  {deck:20s} win-piece n={a['n']:3d} soon={100*a['soon']/a['n']:3.0f}%   nonwin-piece n={b['n']:3d} soon={100*b['soon']/b['n']:3.0f}%")
        for k in ("win", "nonwin"): W[k+"n"] += cc[k]["n"]; W[k+"s"] += cc[k]["soon"]
print("decks with both (pooled):", f"win {W['wins']}/{W['winn']} ({100*W['wins']/W['winn']:.0f}%)  nonwin {W['nonwins']}/{W['nonwinn']} ({100*W['nonwins']/W['nonwinn']:.0f}%)")
