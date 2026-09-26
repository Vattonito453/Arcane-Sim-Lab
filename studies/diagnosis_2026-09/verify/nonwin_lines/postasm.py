import json, glob, re, collections, os
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
for arm, d in ARMS.items():
    agg = collections.Counter(); won = collections.Counter(); lines_asm_games = collections.Counter()
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        m = POD.search(os.path.basename(f))
        if not m: continue
        pf = (glob.glob(ROOT + d + f"/plans_{m.group(1)}.json") + glob.glob(ROOT + d + f"/plans/plans_{m.group(1)}.json"))[0]
        decks = json.load(open(pf, encoding="utf-8"))["decks"]
        zone = {}; cur = None; results = {}; pending = []
        for line in open(f, encoding="utf-8"):
            if '"rec":"zone"' in line:
                r = json.loads(line)
                if r["game"] != cur: zone = {}; cur = r["game"]
                zone[r["cardId"]] = (r["to"], r.get("toPlayer"), r["card"]); continue
            if '"rec":"result"' in line:
                r = json.loads(line); results[r["game"]] = r; continue
            if '"search_seen"' in line:
                r = json.loads(line)
                if r["game"] != cur: zone = {}; cur = r["game"]
                p = r["player"]; plan = decks.get(p.split("-", 1)[1], {})
                B = {nm for (zn, ctl, nm) in zone.values() if zn == "Battlefield" and ctl == p}
                asm = [l for l in plan.get("lines", []) if set(l["cards"]) <= B]
                wasm = [l for l in asm if WIN.search(" ; ".join(l["produces"]))]
                pending.append((r["game"], p, bool(asm), bool(wasm)))
        for g, p, a, w in pending:
            agg["all"] += 1
            if a:
                agg["post"] += 1
                if not w: agg["post_nonwin_only"] += 1
                won["post"] += results.get(g, {}).get("winner") == p
    print(f"{arm:12s} plan searches={agg['all']} post-assembly={agg['post']} ({100*agg['post']/agg['all']:.0f}%) only-nonwin-assembled={agg['post_nonwin_only']} seat-won-in-those={won['post']}")
