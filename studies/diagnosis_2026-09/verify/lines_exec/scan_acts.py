"""Scan raw shim JSONL for repeated non-mana activations / casts per turn of
Spellbook line pieces in the human_ceiling cEDH decks. Read-only."""
import glob, json, os, re, collections, sys
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
lines = json.load(open("all_lines.json"))
deck_lines = collections.defaultdict(list)
for r in lines:
    deck_lines[(r["pod"], r["deck"])].append(r)
piece_decks = collections.defaultdict(set)
for (pod, deck), ls in deck_lines.items():
    for l in ls:
        for c in l["cards"]:
            piece_decks[(pod, deck)].add(c)
TURN = re.compile(r"^Turn (\d+) \((.+)\)$")
ACT = re.compile(r"^(Ai\(\d\)-\S+) (activated|cast) (.+?)(?: targeting .*)?$")
files = [f for f in glob.glob(ROOT + "/**/*.jsonl", recursive=True)]
out = []
agentcounts = collections.Counter()
nfiles = 0
for f in files:
    meta = None; seatdeck = {}
    per = collections.Counter()
    winners = {}
    turnof = {}
    try:
        fh = open(f, encoding="utf-8")
    except Exception:
        continue
    cur = {}
    for line in fh:
        try:
            r = json.loads(line)
        except Exception:
            continue
        rec = r.get("rec")
        if rec == "meta":
            meta = r
            decks = r.get("decks") or []
            players = r.get("players") or []
            for p, d in zip(players, decks):
                dd = d.replace("\\", "/")
                if "human_ceiling/decks/" not in dd:
                    continue
                parts = dd.split("/")
                pod = parts[-3]; deck = parts[-1][:-4]
                seatdeck[p] = (pod, deck)
            if not seatdeck:
                break
            continue
        if not seatdeck:
            continue
        g = r.get("game")
        if rec == "entry":
            t = r.get("type"); m = r.get("message", "")
            if t == "TURN":
                mm = TURN.match(m)
                if mm:
                    cur[g] = (int(mm.group(1)), mm.group(2))
            elif t == "STACK_ADD":
                mm = ACT.match(m)
                if mm and mm.group(1) in seatdeck:
                    card = r.get("card") or mm.group(3)
                    pd = seatdeck[mm.group(1)]
                    if card in piece_decks[pd]:
                        per[(g, cur.get(g, (0, ''))[0], mm.group(1), mm.group(2), card)] += 1
        elif rec == "result":
            winners[g] = (r.get("winner"), r.get("turns"))
        elif rec == "agent":
            agentcounts[r.get("event")] += 1
    if not seatdeck:
        continue
    nfiles += 1
    agents = (meta or {}).get("agents")
    for (g, turn, pl, verb, card), n in per.items():
        w = winners.get(g, (None, None))
        idx = (meta.get("players") or []).index(pl) if pl in (meta.get("players") or []) else -1
        out.append({"file": os.path.relpath(f, ROOT), "game": g, "turn": turn, "player": pl,
                    "agent": agents[idx] if agents and idx >= 0 else None,
                    "verb": verb, "card": card, "n": n, "won": w[0] == pl, "final_turn": w[1]})
json.dump(out, open("acts.json", "w"))
print("cEDH files scanned:", nfiles)
act = [o for o in out if o["verb"] == "activated"]
print("activation rows:", len(act))
mx = collections.defaultdict(lambda: (0, None))
for o in act:
    if o["n"] > mx[o["card"]][0]:
        mx[o["card"]] = (o["n"], o)
for c, (n, o) in sorted(mx.items(), key=lambda x: -x[1][0])[:40]:
    print(f"{n:4d}  {c:40s} {o['agent']} won={o['won']} {o['file']} g{o['game']} t{o['turn']}")
