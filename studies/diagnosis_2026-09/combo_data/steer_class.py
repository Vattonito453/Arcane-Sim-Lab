import json, glob, re, collections
from pathlib import Path
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
audit = {r["deck"]: r for r in json.load(open("plan_audit.json")) if "/" in r["deck"]}
res = collections.Counter(); mode_ct = collections.Counter(); tc = collections.Counter()
for f in glob.glob(R + "/**/*.jsonl", recursive=True):
    with open(f, encoding="utf-8", errors="replace") as fh:
        try: meta = json.loads(fh.readline())
        except: continue
        if meta.get("rec") != "meta" or not meta.get("decks"): continue
        seat = {}
        for p, d in zip(meta["players"], meta["decks"]):
            if "human_ceiling" in d:
                parts = Path(d.replace("\\", "/")).parts; t = parts[-3] + "/" + Path(d).stem
                if t in audit: seat[p] = t
        for line in fh:
            if '"tutor_steer"' not in line and '"tutor_cast"' not in line: continue
            r = json.loads(line); t = seat.get(r.get("player"))
            if not t: continue
            if r["event"] == "tutor_steer":
                m = re.search(r"mode=(\w+).*steer=(.+?) over=", r["detail"])
                if not m: continue
                mode, card = m.group(1), m.group(2)
            else:
                m = re.match(r"^(.+) seeking (.+)$", r["detail"])
                if not m: continue
                mode, card = "tutor_cast_seek", m.group(2)
            win = any(card in a["cards"] for a in audit[t]["lines"] if a["cls"] == "win")
            resl = any(card in a["cards"] for a in audit[t]["lines"] if a["cls"] == "resource")
            cls = "win-line piece" if win else ("resource-only-line piece" if resl else "not a line piece")
            res[(mode, cls)] += 1
for k, v in sorted(res.items()): print(k, v)
