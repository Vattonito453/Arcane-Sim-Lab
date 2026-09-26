import json, glob, re, collections, hashlib
from pathlib import Path
R = "C:/Users/Vatto/Magic Rules Engine/studies"
seen = set()
stats = collections.defaultdict(lambda: collections.Counter())
act_by_game = collections.Counter()
for f in glob.glob(R + "/**/*.jsonl", recursive=True):
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
            if "magda" in stem:
                ag = (meta.get("agents") or ["?"]*4)[i]
                seats[p] = (stem, ag)
        if not seats: continue
        games = set(); onbf = set(); acts = collections.Counter(); wins = set(); portal_bf=set()
        for line in fh:
            if '"rec":"result"' in line:
                r = json.loads(line); games.add(r["game"])
                if r.get("winner") in seats: wins.add((r["game"], r["winner"]))
                continue
            if "Clock of Omens" not in line and "Portal to Phyrexia" not in line: continue
            r = json.loads(line)
            if r.get("rec") == "zone" and r.get("to") == "Battlefield" and r.get("toPlayer") in seats:
                if r.get("card") == "Clock of Omens": onbf.add((r["game"], r["toPlayer"]))
                if r.get("card") == "Portal to Phyrexia": portal_bf.add((r["game"], r["toPlayer"]))
            if r.get("rec") == "entry" and r.get("type") == "STACK_ADD":
                m = re.match(r"^(Ai\(\d\)-\S+) activated Clock of Omens", r.get("message", ""))
                if m and m.group(1) in seats: acts[(r["game"], m.group(1))] += 1
        for p, (stem, ag) in seats.items():
            key = (stem, ag)
            for g in games:
                s = stats[key]; s["games"] += 1
                if (g, p) in onbf: s["clock_bf"] += 1
                if acts[(g, p)]: s["clock_act_games"] += 1; s["acts"] += acts[(g, p)]
                if (g, p) in onbf and (g, p) in wins: s["win_with_clock"] += 1
                if (g, p) in wins: s["wins"] += 1
                if (g, p) in portal_bf: s["portal_bf"] += 1
                if (g, p) in portal_bf and (g,p) in wins: s["win_with_portal"] += 1
                if acts[(g,p)] and (g,p) in wins: s["win_with_clock_act"] += 1
tot = collections.Counter()
for k, s in sorted(stats.items()):
    print(k, dict(s))
    if k[0] == "magda":
        tot.update(s)
print("magda total", dict(tot))
