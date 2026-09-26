# How eliminations actually happen: combat damage vs non-combat damage vs life loss vs other,
# per pilot of the WINNING seat, on cEDH runs. analysis.win_method lumps combat and life loss together.
import os, json, glob, re, collections, sys
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
LOST = re.compile(r"^(Ai\(\d\)-.+?) has lost (?:because|due to)\s*(?:of\s+)?(.+?)\.?\s*$")
DMG = re.compile(r"deals (\d+) (combat |non-combat )?damage to (Ai\(\d\)-[^.]+)\.")
LIFE = re.compile(r"^Life: (Ai\(\d\)-.+?) (-?\d+) > (-?\d+)")
for d in sys.argv[1:]:
    tally = collections.Counter()
    for p in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
        agents = {}
        cur = collections.defaultdict(list)  # game -> events
        results = {}
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"rec":"meta"'):
                    m = json.loads(line); agents = dict(zip(m["players"], m.get("agents") or ["stock"]*4))
                elif line.startswith('{"rec":"entry"') and ('"DAMAGE"' in line or '"LIFE"' in line or '"GAME_OUTCOME"' in line):
                    e = json.loads(line); cur[e["game"]].append(e)
                elif line.startswith('{"rec":"result"'):
                    r = json.loads(line); results[r["game"]] = r
        for g, evs in cur.items():
            r = results.get(g)
            if not r or not r.get("winner"): continue
            wp = agents.get(r["winner"], "stock")
            lastdmg = {}  # player -> (seq, kind)
            for e in evs:
                msg = e["message"]
                if e["type"] == "DAMAGE":
                    m = DMG.search(msg)
                    if m: lastdmg[m.group(3)] = (e["seq"], "combat" if m.group(2) == "combat " else "noncombat_damage")
                elif e["type"] == "LIFE":
                    m = LIFE.match(msg)
                    if m and int(m.group(3)) < int(m.group(2)):
                        pl = m.group(1)
                        ld = lastdmg.get(pl)
                        kind = ld[1] if ld and e["seq"] - ld[0] <= 3 else "life_loss"
                        lastdmg[pl + "#life"] = kind
                elif e["type"] == "GAME_OUTCOME":
                    m = LOST.match(msg)
                    if m:
                        pl, reason = m.group(1), m.group(2)
                        if "life total" in reason:
                            kind = lastdmg.get(pl + "#life", "unknown")
                        elif "poison" in reason: kind = "poison"
                        elif "commander" in reason or "general" in reason: kind = "commander_damage"
                        elif "draw" in reason or "library" in reason: kind = "deckout"
                        elif "spell" in reason: kind = "spell_win"
                        else: kind = "other:" + reason[:40]
                        tally[(wp, kind)] += 1
    print("==", d)
    for pil in ("plan", "stock"):
        sub = {k[1]: v for k, v in tally.items() if k[0] == pil}
        n = sum(sub.values())
        if n: print(f"   winner={pil:5s} eliminations={n}: " + ", ".join(f"{k} {v} ({100*v/n:.0f}%)" for k, v in sorted(sub.items(), key=lambda kv: -kv[1])))
