import json, glob, re, collections, hashlib
from pathlib import Path
R = "C:/Users/Vatto/Magic Rules Engine/studies"
seen = set()
S = collections.defaultdict(collections.Counter)
srcs = collections.Counter(); pick_src = collections.Counter()
for f in sorted(glob.glob(R + "/**/*.jsonl", recursive=True)):
    h = hashlib.md5(open(f, "rb").read()).hexdigest()
    if h in seen: continue
    seen.add(h)
    with open(f, encoding="utf-8", errors="replace") as fh:
        try: meta = json.loads(fh.readline())
        except Exception: continue
        if meta.get("rec") != "meta" or not meta.get("decks"): continue
        seats = {}
        for i, (p, d) in enumerate(zip(meta["players"], meta["decks"])):
            stem = Path(d.replace("\\", "/")).stem
            if stem == "magda":
                seats[p] = (meta.get("agents") or ["?"]*4)[i]
        if not seats: continue
        sd = str(Path(f).relative_to(R).parent).replace("\\", "/")
        nplan = sum(1 for a in (meta.get("agents") or []) if a == "plan")
        games=set(); wins=set(); pbf=set(); steerP=collections.Counter(); seenP=collections.Counter(); portal_first=set()
        for line in fh:
            if '"rec":"result"' in line:
                r = json.loads(line); games.add(r["game"])
                if r.get("winner") in seats: wins.add((r["game"], r["winner"]))
                continue
            if "Portal to Phyrexia" not in line: continue
            r = json.loads(line)
            gp = (r.get("game"), r.get("toPlayer") or r.get("player"))
            if r.get("rec") == "zone" and r.get("card") == "Portal to Phyrexia" and r.get("to") == "Battlefield" and r.get("toPlayer") in seats:
                pbf.add(gp)
            if r.get("rec") == "agent" and r.get("player") in seats:
                if r["event"] == "tutor_steer" and ("over=Portal to Phyrexia" in r["detail"] or r["detail"].endswith("over Portal to Phyrexia")):
                    steerP[gp] += 1
                if r["event"] == "search_seen" and "picked=Portal to Phyrexia" in r["detail"]:
                    seenP[gp] += 1
                    m = re.search(r"src=(.+)$", r["detail"]); pick_src[m.group(1) if m else "?"] += 1
        for p, ag in seats.items():
            k = (sd, ag, nplan)
            for g in games:
                s = S[k]; s["games"] += 1
                s["wins"] += (g, p) in wins
                s["portal_bf"] += (g, p) in pbf
                s["win&portal"] += ((g, p) in wins and (g, p) in pbf)
                s["games_steered_over_portal"] += bool(steerP[(g, p)])
                s["steers_over_portal"] += steerP[(g, p)]
                s["stock_picked_portal_seen"] += seenP[(g, p)]
                s["portal_bf_after_steer_game"] += bool(steerP[(g,p)]) and (g,p) in pbf
for k, s in sorted(S.items()):
    print(k, dict(s))
print("search_seen picked=Portal src:", pick_src.most_common(10))
