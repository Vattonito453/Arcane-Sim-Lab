import json, glob, os, re, collections, sys
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
files = sorted(glob.glob(ROOT + "/**/*.jsonl", recursive=True))
agg = collections.defaultdict(collections.Counter)
oracle_wins = []   # (dir, file, game, player, agentType)
decks = []
oracle_cc = collections.defaultdict(collections.Counter)  # dir -> detail
all_cc = collections.Counter()
for f in files:
    d = os.path.relpath(os.path.dirname(f), ROOT).replace("\\", "/")
    seat = {}
    shim = None
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            if '"rec":"meta"' in line:
                r = json.loads(line); shim = r.get("shim")
                for p, a in zip(r.get("players", []), r.get("agents", [])):
                    seat[p] = a
                continue
            if '"GAME_OUTCOME"' in line:
                r = json.loads(line); m = r["message"]
                mm = re.match(r"(Ai\(\d\)-.+?) has (won|lost) (.*)", m)
                if not mm: continue
                p, wl, why = mm.groups()
                a = seat.get(p, "?")
                if wl == "won" and "Thassa's Oracle" in why:
                    oracle_wins.append((d, os.path.basename(f), r["game"], p, a, shim))
                if "empty library" in why:
                    decks.append((d, os.path.basename(f), r["game"], p, a, shim))
                continue
            if '"rec":"agent"' in line and '"combo_cast"' in line:
                r = json.loads(line)
                det = r["detail"]
                all_cc[d] += 1
                if det.startswith("Thassa's Oracle"):
                    oracle_cc[d][det] += 1
print("combo_cast by dir:", dict(all_cc))
print("sum", sum(all_cc.values()))
print("\nOracle combo_casts by dir:")
tot = collections.Counter()
for d, c in oracle_cc.items():
    print(d, dict(c)); tot.update(c)
print("TOTAL oracle cc", dict(tot), sum(tot.values()))
print("\nOracle wins by dir/agent:")
print(collections.Counter((w[0], w[4]) for w in oracle_wins))
print("total", len(oracle_wins), collections.Counter(w[4] for w in oracle_wins))
print("\nEmpty-library losses by dir/agent:")
print(collections.Counter((w[0], w[4]) for w in decks))
print("total", len(decks), collections.Counter(w[4] for w in decks))
json.dump({"wins": oracle_wins, "decks": decks}, open(os.path.join(os.path.dirname(__file__), "v1_out.json"), "w"))
