"""What analysis.py would call a 'converted' combo (assembled, then the seat won
by ANY method) vs whether the line's loop actually ran (>=5 stack items from
one line piece in a single turn at or after assembly) and how the game ended."""
import json, glob, re, collections, os

HERE = os.path.dirname(os.path.abspath(__file__))
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_*.jsonl", "agent_viability/runs_winmax/cell_*.jsonl",
        "agent_viability/runs_016_engine/cell_*.jsonl", "behavior_rubric/runs_agent_shipping/*.jsonl",
        "tutor_targeting/runs_stage2/*.jsonl", "human_ceiling/runs/*.jsonl"]
act = collections.Counter()
for pat in PATS:
    for f in glob.glob(S + pat):
        rel = os.path.relpath(f, S).replace(os.sep, "/")
        t = 0
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            if r.get("rec") != "entry":
                continue
            if r["type"] == "TURN":
                t = int(re.match(r"Turn (\d+)", r["message"]).group(1))
            m = re.match(r"(Ai\(\d\)-\S+) (activated|triggered) (.+?)(?: targeting .*)?$", r["message"])
            if m and r["type"] == "STACK_ADD":
                act[(rel, r["game"], m.group(1), t, r.get("card"))] += 1
rows = json.load(open(os.path.join(HERE, "funnel_rows.json"), encoding="utf-8"))
cls = json.load(open(os.path.join(HERE, "line_classes.json"), encoding="utf-8"))
cmap = {tuple(sorted(c["cards"])): c for c in cls if not c.get("uncached")}
res = collections.Counter()
per_seat = collections.Counter()
for r in rows:
    best = None
    for ln in r["lines"]:
        if ln["assembled"] is None or not r["won"]:
            continue
        c = cmap.get(tuple(sorted(ln["line"].split(" + "))))
        if not c:
            continue
        mx = 0
        for t in range(ln["assembled"], r["final_turn"] + 1):
            for card in c["cards"]:
                mx = max(mx, act.get((r["file"], r["game"], r["seat"], t, card), 0))
        spell = r["method"].startswith("spell")
        k = (c["class"].split(" (")[0],
             "loop ran" if mx >= 5 else "loop never ran",
             "won by spell" if spell else "won by combat/life/other")
        res[k] += 1
        ran = mx >= 5 or spell
        best = ran if best is None else (best or ran)
    if best is not None:
        per_seat["seat-game counted converted; line actually executed" if best
                 else "seat-game counted converted; NO line executed"] += 1
print("assembled-line instances in games the seat won:", sum(res.values()))
for k, v in res.most_common():
    print(f"{v:4d} {k}")
print(dict(per_seat))
