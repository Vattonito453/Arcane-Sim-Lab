# Per game-seat timeline for every seat that CAST Thassa's Oracle (any study).
import json, glob, os, re, collections
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
EXILERS = ("Demonic Consultation", "Tainted Pact")
files = sorted(glob.glob(ROOT + "/**/*.jsonl", recursive=True))
rows = []
for f in files:
    d = os.path.relpath(os.path.dirname(f), ROOT).replace("\\", "/")
    seat = {}; shim = None
    games = collections.defaultdict(list)   # game -> list of entries (ordered)
    agent = collections.defaultdict(list)
    has_oracle = False
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            if '"rec":"meta"' in line:
                r = json.loads(line); shim = r.get("shim")
                seat = dict(zip(r.get("players", []), r.get("agents", [])))
                continue
            if '"rec":"entry"' in line:
                if ('"TURN"' in line or "Thassa's Oracle" in line or "Consultation" in line
                        or "Tainted Pact" in line or "GAME_OUTCOME" in line):
                    r = json.loads(line); games[r["game"]].append(r)
                    if "cast Thassa's Oracle" in line: has_oracle = True
                continue
            if '"rec":"agent"' in line and ('combo_' in line or 'tutor_' in line):
                r = json.loads(line); agent[(r["game"], r["player"])].append((r["turn"], r["event"], r["detail"]))
    if not has_oracle: continue
    for g, ents in games.items():
        ents.sort(key=lambda r: r["seq"])
        turn = 0
        per = collections.defaultdict(list)
        outcome = {}
        trig_open = {}   # player -> True while oracle trigger on stack
        for r in ents:
            m = r["message"]
            if r["type"] == "TURN":
                mm = re.match(r"Turn (\d+)", m); turn = int(mm.group(1)); continue
            if r["type"] == "GAME_OUTCOME":
                mm = re.match(r"(Ai\(\d\)-.+?) has (won|lost) (.*)", m)
                if mm: outcome[mm.group(1)] = mm.group(2) + " " + mm.group(3)
                continue
            mm = re.match(r"(Ai\(\d\)-.+?) cast (Thassa's Oracle|Demonic Consultation|Tainted Pact)$", m)
            if r["type"] == "STACK_ADD" and mm:
                p, c = mm.groups()
                per[p].append((turn, r["seq"], "cast " + c + (" [ORACLE TRIGGER ON STACK]" if trig_open.get(p) else "")))
                continue
            mm = re.match(r"(Ai\(\d\)-.+?) triggered Thassa's Oracle", m)
            if r["type"] == "STACK_ADD" and mm:
                trig_open[mm.group(1)] = True
                per[mm.group(1)].append((turn, r["seq"], "oracle trigger"))
                continue
            if r["type"] == "STACK_RESOLVE" and m.startswith("When Thassa's Oracle enters"):
                # whose? the most recent open trigger
                for p in list(trig_open):
                    if trig_open[p]:
                        trig_open[p] = False
                        per[p].append((turn, r["seq"], "oracle trigger resolves"))
                continue
        for p, evs in per.items():
            if not any("cast Thassa's Oracle" in e[2] for e in evs): continue
            rows.append({"dir": d, "file": os.path.basename(f), "game": g, "player": p,
                         "agent": seat.get(p, "?"), "shim": shim, "events": evs,
                         "outcome": outcome.get(p, "none/draw-or-alive"),
                         "agentlog": agent.get((g, p), [])})
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_rows.json"), "w"), indent=1)
print(len(rows), "game-seats cast Thassa's Oracle")
print(collections.Counter(r["agent"] for r in rows))
