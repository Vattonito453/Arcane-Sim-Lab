import json, glob, re, collections
from pathlib import Path
R = "C:/Users/Vatto/Magic Rules Engine/studies/agent_viability"
S = collections.defaultdict(collections.Counter); rounds = collections.defaultdict(list)
for f in sorted(glob.glob(R + "/runs_*/*.jsonl")):
    fh = open(f, encoding="utf-8", errors="replace")
    try: meta = json.loads(fh.readline())
    except Exception: continue
    if meta.get("rec") != "meta" or not meta.get("decks"): continue
    arm = Path(f).parent.name
    seats = {p: meta["agents"][i] for i, (p, d) in enumerate(zip(meta["players"], meta["decks"])) if Path(d.replace("\\","/")).stem == "magda"}
    if not seats: continue
    games=set(); wins=set(); pbf={}; lib2bf=set(); seenP=set(); steer=set()
    for line in fh:
        if '"rec":"result"' in line:
            r=json.loads(line); games.add(r["game"])
            if r.get("winner") in seats: wins.add((r["game"], r["winner"]))
            continue
        if "Portal to Phyrexia" not in line: continue
        r=json.loads(line)
        if r.get("rec")=="zone" and r.get("card")=="Portal to Phyrexia" and r.get("to")=="Battlefield" and r.get("toPlayer") in seats:
            gp=(r["game"], r["toPlayer"]); pbf.setdefault(gp, r["turn"])
            if r.get("from")=="Library": lib2bf.add(gp)
        if r.get("rec")=="agent" and r.get("player") in seats:
            gp=(r["game"], r["player"])
            if r["event"]=="search_seen" and "picked=Portal to Phyrexia" in r["detail"]: seenP.add(gp)
            if r["event"]=="tutor_steer" and "over=Portal to Phyrexia" in r["detail"]: steer.add(gp)
    for p, ag in seats.items():
        for g in games:
            gp=(g,p); s=S[ag]
            s["games"]+=1; s["wins"]+=gp in wins; s["portal_bf"]+=gp in pbf; s["portal_lib2bf"]+=gp in lib2bf
            s["stock_would_fetch_portal"]+=gp in seenP; s["steered_over"]+=gp in steer
            if gp in seenP:
                s["swf_and_win"]+=gp in wins; s["swf_and_bf"]+=gp in pbf
            if gp in lib2bf: s["lib2bf_and_win"]+=gp in wins
for k,s in S.items(): print(k, dict(s))
