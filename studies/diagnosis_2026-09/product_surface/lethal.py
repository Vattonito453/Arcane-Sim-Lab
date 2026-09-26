"""For games the product labels 'combat damage' (loss reason 'life total reached 0'),
find what actually dealt the lethal life loss to each eliminated player."""
import json, sys, re, collections, glob
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import analysis
RE_LIFE = re.compile(r"^Life:\s*(.+?)\s+(-?\d+)\s*>\s*(-?\d+)")
RE_LOST = re.compile(r"^(.+?) has lost because life total reached 0")
def classify(game):
    flat = []
    for t in game.get("turns") or []:
        for e in t.get("events") or []:
            flat.append((t.get("turn"), e))
    out = []
    losers = set()
    for _, e in flat:
        if e.get("action") == "game_outcome":
            m = RE_LOST.match(e.get("raw",""))
            if m: losers.add(m.group(1).strip())
    for who in losers:
        idx = None
        for i in range(len(flat)-1, -1, -1):
            e = flat[i][1]
            if e.get("action") == "life_change":
                m = RE_LIFE.match(e.get("raw",""))
                if m and m.group(1).strip() == who and int(m.group(3)) <= 0 and int(m.group(2)) > 0:
                    idx = i; break
        if idx is None:
            out.append((who, "no_lethal_line", "")); continue
        kind, src = "unknown", ""
        for j in range(idx-1, max(-1, idx-6), -1):
            e = flat[j][1]; raw = e.get("raw","")
            if e.get("action") == "damage" and who in raw:
                kind = "combat" if " combat damage" in raw and "non-combat" not in raw else "noncombat_damage"
                src = raw.split(" deals ")[0]; break
            if e.get("action") in ("stack_resolve",):
                kind = "life_loss_effect"; src = raw[:70]; break
        out.append((who, kind, src))
    return out
tot = collections.Counter(); games_tot = collections.Counter(); srcs = collections.Counter()
for p in sys.argv[1:]:
    r = json.load(open(p, encoding="utf-8"))
    for g in r.get("games") or []:
        wm = analysis.win_method(g)
        if wm["method"] != "combat damage / life loss": continue
        games_tot["games_labelled_combat"] += 1
        res = classify(g)
        kinds = [k for _, k, _ in res]
        for w, k, s in res:
            tot[k] += 1
            if k != "combat": srcs[s[:50]] += 1
        # final kill = the game's last elimination: use last lethal line overall
        if kinds and all(k == "combat" for k in kinds): games_tot["all_eliminations_combat"] += 1
        elif kinds and any(k == "combat" for k in kinds): games_tot["mixed"] += 1
        else: games_tot["no_combat_elimination"] += 1
print("eliminations:", dict(tot))
print("games:", dict(games_tot))
print("top non-combat lethal sources:", srcs.most_common(15))
