"""Zone-truth assembly vs conversion of every plan line, from raw shim JSONL
(cEDH pods only). Seat kinds: plan vs stock. Line classes from plan_audit."""
import json, glob, re, collections
from pathlib import Path
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
audit = {r["deck"]: r for r in json.load(open("plan_audit.json")) if "/" in r["deck"]}
files = [f for f in glob.glob(R + "/**/*.jsonl", recursive=True)]
stats = collections.defaultdict(collections.Counter)   # (seatkind, cls) -> counters
lag = collections.defaultdict(list)
by_line = collections.defaultdict(collections.Counter)
nfiles = 0
for f in files:
    meta = None
    try:
        fh = open(f, encoding="utf-8", errors="replace")
    except OSError: continue
    first = fh.readline()
    try: meta = json.loads(first)
    except: fh.close(); continue
    if meta.get("rec") != "meta" or not meta.get("decks"): fh.close(); continue
    seatdeck = {}
    for p, d, a in zip(meta["players"], meta["decks"], meta.get("agents") or ["stock"]*4):
        parts = Path(d.replace("\\", "/")).parts
        tag = parts[-3] + "/" + Path(d).stem if "human_ceiling" in d else None
        if tag in audit: seatdeck[p] = (tag, a)
    if not seatdeck: fh.close(); continue
    nfiles += 1
    bf = collections.defaultdict(dict)   # game -> player -> {cardId: name}
    assembled = {}                        # (g, player, lineidx) -> turn
    winners = {}; methods = {}; games = set()
    for line in fh:
        try: r = json.loads(line)
        except: continue
        rec = r.get("rec"); g = r.get("game")
        if rec == "zone":
            games.add(g)
            if r.get("from") == "Battlefield":
                bf[g].setdefault(r.get("fromPlayer"), {}).pop(r.get("cardId"), None)
            if r.get("to") == "Battlefield":
                p = r.get("toPlayer"); bf[g].setdefault(p, {})[r.get("cardId")] = r.get("card")
                if p in seatdeck:
                    names = set(bf[g][p].values())
                    for i, ln in enumerate(audit[seatdeck[p][0]]["lines"]):
                        if (g, p, i) in assembled: continue
                        if all((c in names) or (c.split(" // ")[0] in names) for c in ln["cards"]):
                            assembled[(g, p, i)] = r.get("turn")
        elif rec == "result":
            winners[g] = (r.get("winner"), r.get("turns"))
        elif rec == "entry" and r.get("type") == "GAME_OUTCOME":
            m = r.get("message", "")
            if " has won" in m: methods[g] = m
    fh.close()
    for g in winners:
        for p, (tag, a) in seatdeck.items():
            for i, ln in enumerate(audit[tag]["lines"]):
                allB = all(z == "B" for z in ln["zones"].values()) if ln["zones"] else None
                cls = ln["cls"] + ("" if allB else "/nonB")
                k = (a, cls)
                stats[k]["seat_games"] += 1
                if (g, p, i) in assembled:
                    stats[k]["assembled"] += 1
                    w, turns = winners[g]
                    if w == p:
                        stats[k]["won_after"] += 1
                        lag[k].append((turns or 0) - (assembled[(g, p, i)] or 0))
                    by_line[(tag, " + ".join(ln["cards"]), ln["cls"])]["asm"] += 1
                    if winners[g][0] == p: by_line[(tag, " + ".join(ln["cards"]), ln["cls"])]["won"] += 1
print("files with cEDH seats:", nfiles)
print("seat kind, line class -> seat-games, assembled, seat won that game, median player-turns from assembly to end")
import statistics
for k in sorted(stats):
    s = stats[k]; L = lag[k]
    print(f"  {k}: {s['seat_games']} seat-line-games, assembled {s['assembled']}, won {s['won_after']}"
          + (f", median lag {statistics.median(L)} player-turns" if L else ""))
print("\nMost-assembled lines:")
for k, v in sorted(by_line.items(), key=lambda kv: -kv[1]["asm"])[:30]:
    print(f"  asm {v['asm']:3d} won {v['won']:3d}  [{k[2]}] {k[0]}: {k[1]}")
print("\nLag distribution (player-turns from first assembly to game end, seat won):")
for k in sorted(lag):
    L = lag[k]
    if not L: continue
    same = sum(1 for x in L if x <= 0); one_round = sum(1 for x in L if x <= 4)
    print(f"  {k}: n={len(L)}  same player-turn {same} ({same/len(L):.0%}), within 4 player-turns (~1 round) {one_round} ({one_round/len(L):.0%})")
