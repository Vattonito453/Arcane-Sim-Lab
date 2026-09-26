# Game-level win method = kind of the LAST elimination, plus what caused non-combat final blows.
import os, json, glob, re, collections, sys
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
LOST = re.compile(r"^(Ai\(\d\)-.+?) has lost (?:because|due to)\s*(?:of\s+)?(.+?)\.?\s*$")
DMG = re.compile(r"^(.+?) \(\d+\) deals (\d+) (combat |non-combat )?damage to (Ai\(\d\)-[^.]+)\.")
LIFE = re.compile(r"^Life: (Ai\(\d\)-.+?) (-?\d+) > (-?\d+)")
SPELL = re.compile(r"won by spell '([^']+)'")
for d in sys.argv[1:]:
    games = collections.Counter(); causes = collections.Counter()
    for p in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
        agents = {}; evs = collections.defaultdict(list); results = {}
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"rec":"meta"'):
                    m = json.loads(line); agents = dict(zip(m["players"], m.get("agents") or ["stock"]*4))
                elif line.startswith('{"rec":"entry"'):
                    e = json.loads(line)
                    if e["type"] in ("DAMAGE","LIFE","GAME_OUTCOME","STACK_RESOLVE","STACK_ADD"): evs[e["game"]].append(e)
                elif line.startswith('{"rec":"result"'):
                    r = json.loads(line); results[r["game"]] = r
        for g, es in evs.items():
            r = results.get(g)
            if not r or not r.get("winner"): continue
            wp = agents.get(r["winner"], "stock")
            lastdmg = {}; lastlife = {}; lastres = None; final = None
            for e in es:
                msg = e["message"]
                if e["type"] in ("STACK_RESOLVE","STACK_ADD"): lastres = msg[:70]
                elif e["type"] == "DAMAGE":
                    m = DMG.match(msg)
                    if m: lastdmg[m.group(4)] = (e["seq"], "combat" if m.group(3) == "combat " else "noncombat_damage", m.group(1))
                elif e["type"] == "LIFE":
                    m = LIFE.match(msg)
                    if m and int(m.group(3)) < int(m.group(2)):
                        ld = lastdmg.get(m.group(1))
                        lastlife[m.group(1)] = (ld[1], ld[2]) if ld and e["seq"] - ld[0] <= 3 else ("life_loss", lastres)
                elif e["type"] == "GAME_OUTCOME":
                    sm = SPELL.search(msg)
                    if sm: final = ("spell_win", sm.group(1)); continue
                    m = LOST.match(msg)
                    if m and final is None or (m and final and final[0] != "spell_win"):
                        pl, reason = m.group(1), m.group(2)
                        if "life total" in reason: final = lastlife.get(pl, ("unknown", None))
                        else: final = (reason[:30], None)
            if final:
                games[(wp, final[0])] += 1
                if final[0] != "combat": causes[(wp, final[0], final[1])] += 1
    print("==", d)
    for pil in ("plan","stock"):
        sub = {k[1]: v for k, v in games.items() if k[0] == pil}; n = sum(sub.values())
        if n: print(f"   winner={pil:5s} games={n}: " + ", ".join(f"{k} {v} ({100*v/n:.0f}%)" for k, v in sorted(sub.items(), key=lambda kv: -kv[1])))
    for k, v in causes.most_common(8): print("      ", v, k)
