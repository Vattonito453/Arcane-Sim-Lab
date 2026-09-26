# Assembled-vs-converted on cEDH pods, from shim zone records, per pilot.
# Assembled = every card of an all-permanent Spellbook line on the seat's battlefield at once.
import os, json, glob, re, collections, sys
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
def strip(n): return re.sub(r"^Ai\(\d\)-", "", n)
LINES = {}
for pf in glob.glob(os.path.join(ROOT, "behavior_rubric", "plans_*.json")) + glob.glob(os.path.join(ROOT, "agent_viability", "*", "plans_*.json")):
    d = json.load(open(pf))["decks"]
    for deck, plan in d.items():
        if deck not in LINES and plan.get("lines"):
            LINES[deck] = [tuple(l["cards"]) for l in plan["lines"]]
NONPERM = {"Instant", "Sorcery"}
def run(dirs):
    tot = collections.defaultdict(collections.Counter)
    delays = collections.defaultdict(list)
    for d in dirs:
        for p in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
            agents = {}; players = []
            bf = {}  # game -> {cardId: (name, ctl)}
            types = {}
            assembled = {}  # (game, seat) -> first turn
            results = {}
            with open(p, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith('{"rec":"meta"'):
                        m = json.loads(line); players = m["players"]; agents = dict(zip(players, m.get("agents") or ["stock"]*4))
                    elif line.startswith('{"rec":"zone"'):
                        z = json.loads(line); g = z["game"]
                        types[z["card"]] = z.get("types", "")
                        b = bf.setdefault(g, {})
                        if z["from"] == "Battlefield": b.pop(z["cardId"], None)
                        if z["to"] == "Battlefield":
                            b[z["cardId"]] = (z["card"], z.get("toPlayer"))
                            ctl = z.get("toPlayer")
                            if ctl is None: continue
                            deck = strip(ctl)
                            if (g, ctl) in assembled or deck not in LINES: continue
                            names = {n for (n, c) in b.values() if c == ctl}
                            for ln in LINES[deck]:
                                if all(c in names for c in ln):
                                    assembled[(g, ctl)] = (z["turn"], ln); break
                    elif line.startswith('{"rec":"result"'):
                        r = json.loads(line); results[r["game"]] = r
            for g, r in results.items():
                for s in players:
                    deck = strip(s)
                    if deck not in LINES: continue
                    pil = agents.get(s, "stock")
                    t = tot[(d.split("/")[0] + ":" + pil)]
                    t["seat_games"] += 1
                    if r.get("winner") == s: t["wins"] += 1
                    if (g, s) in assembled:
                        at, ln = assembled[(g, s)]
                        t["assembled"] += 1
                        if r.get("winner") == s:
                            t["assembled_won"] += 1
                            delays[(d.split("/")[0] + ":" + pil)].append(r["turns"] - at)
                        elif r.get("timedOut"): t["assembled_timeout"] += 1
    for k, t in sorted(tot.items()):
        dl = sorted(delays[k])
        med = dl[len(dl)//2] if dl else None
        print(f"{k:32s} seatGames={t['seat_games']:4d} wins={t['wins']:4d} assembled={t['assembled']:4d} "
              f"({100*t['assembled']/t['seat_games']:.1f}%) assembled&won={t['assembled_won']:3d} "
              f"({100*t['assembled_won']/max(1,t['assembled']):.0f}% of assembled) assembled&timeout={t['assembled_timeout']} "
              f"median Forge-turns assembled->game end (won)={med}")
run(sys.argv[1:])
