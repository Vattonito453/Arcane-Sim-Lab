import json, glob, re, collections
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
files = glob.glob(R + "/**/*.jsonl", recursive=True)
PIECES = ("Thassa's Oracle", "Demonic Consultation", "Tainted Pact")
out = collections.Counter(); samples = []
for f in files:
    games = collections.defaultdict(list)   # game -> list of (seq/order, kind, text)
    results = {}
    with open(f, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if not any(p in line for p in PIECES) and '"rec":"result"' not in line[:20] and "has lost" not in line and "has won" not in line:
                continue
            try: r = json.loads(line)
            except: continue
            g = r.get("game")
            if r.get("rec") == "agent" and r.get("event") in ("combo_cast", "combo_hold"):
                if any(p in r.get("detail","") for p in PIECES):
                    games[g].append((i, "AGENT " + r["event"], r["player"], r["detail"], r.get("turn")))
            elif r.get("rec") == "entry":
                m = r.get("message","")
                if ("cast" in m and any(p in m for p in PIECES)) or "has lost" in m or "has won" in m or ("Oracle" in m and ("win" in m or "look" in m.lower())):
                    games[g].append((i, "LOG " + r.get("type",""), "", m[:220], None))
            elif r.get("rec") == "result":
                results[g] = r
    for g, evs in games.items():
        if not any(e[1].startswith("AGENT combo_cast") for e in evs): continue
        samples.append((f.split("studies")[1], g, evs))
print(len(samples), "games with an agent combo_cast of a Thoracle-line piece")
for f, g, evs in samples[:40]:
    print("====", f, "game", g)
    for e in evs[:14]: print("   ", e[1], e[2], "|", e[3], "| t", e[4])
