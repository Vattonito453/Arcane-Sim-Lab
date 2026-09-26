import json, glob, collections, os, re, sys
root = r"C:/Users/Vatto/Magic Rules Engine/studies"
dirs = sys.argv[1:]
comp = collections.Counter()      # (card, outcome) for completing combo casts
cardtype = {}
summary = collections.Counter()
examples = collections.defaultdict(list)
for d in dirs:
  for f in glob.glob(os.path.join(root, d, "*.jsonl")):
    games = collections.defaultdict(lambda: {"casts": [], "winner": None, "why": [], "types": {}})
    meta_agents = None
    for line in open(f, encoding="utf-8", errors="replace"):
        try: r = json.loads(line)
        except Exception: continue
        rec = r.get("rec")
        if rec == "meta":
            meta_agents = dict(zip(r.get("players", []), r.get("agents", [])))
            continue
        g = r.get("game")
        if rec == "agent" and r.get("event") == "combo_cast":
            m = re.match(r"(.*) \((\d+)/(\d+) online\)", r.get("detail", ""))
            if m: games[g]["casts"].append((r["player"], m.group(1), int(m.group(2)), int(m.group(3)), r.get("turn")))
        elif rec == "result":
            games[g]["winner"] = r.get("winner"); games[g]["draw"] = r.get("draw")
        elif rec == "entry" and r.get("type") == "GAME_OUTCOME":
            games[g]["why"].append(r.get("message", ""))
        elif rec == "zone":
            cardtype[r.get("card")] = r.get("types", "")
    for g, G in games.items():
        done = set()
        for (p, card, k, n, t) in G["casts"]:
            if k + 1 != n: continue
            key = (p, card)
            if key in done: continue
            done.add(key)
            won = G["winner"] == p
            wmsg = [w for w in G["why"] if "has won" in w and p in w]
            how = "none"
            if won:
                m = re.search(r"effect of '([^']*)'", " ".join(wmsg))
                how = ("alt:" + m.group(1)) if m else "other(" + (" ".join(wmsg)[:60]) + ")"
            else:
                how = "draw" if G.get("draw") else "lost"
            comp[(card, how)] += 1
            summary[("perm" if any(x in cardtype.get(card, "") for x in ("Creature","Artifact","Enchantment","Planeswalker","Land")) else "spell", "won" if won else how)] += 1
            if len(examples[card]) < 2: examples[card].append((os.path.basename(f), g, t))
print("completing-cast outcomes by piece kind:")
for k, v in sorted(summary.items()): print(" ", k, v)
print("by card:")
agg = collections.defaultdict(collections.Counter)
for (card, how), v in comp.items(): agg[card][how] += v
for card, c in sorted(agg.items(), key=lambda kv: -sum(kv[1].values()))[:30]:
    print(f"  {sum(c.values()):3d} {card!r:40} [{cardtype.get(card,'?')}] {dict(c)}")
