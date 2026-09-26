import json, sys, re, collections
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import analysis
RE_LIFE = re.compile(r"^Life:\s*(.+?)\s+(-?\d+)\s*>\s*(-?\d+)")
def elim_kinds(g):
    flat = [e for t in g.get("turns") or [] for e in t.get("events") or []]
    kinds = []
    for i, e in enumerate(flat):
        if e.get("action") != "life_change": continue
        m = RE_LIFE.match(e.get("raw",""))
        if not (m and int(m.group(3)) <= 0 < int(m.group(2))): continue
        who = m.group(1).strip()
        k = "noncombat"
        for j in range(i-1, max(-1, i-10), -1):
            r = flat[j].get("raw","")
            if flat[j].get("action") == "damage" and r.rstrip(".").endswith("to " + who):
                k = "combat" if " combat damage to " in r else "noncombat"
                break
            if flat[j].get("action") == "phase": break
        kinds.append(k)
    return kinds
T = collections.Counter()
for p in sys.argv[1:]:
    r = json.load(open(p, encoding="utf-8"))
    for g in r.get("games") or []:
        if analysis.win_method(g)["method"] != "combat damage / life loss": continue
        ks = elim_kinds(g)
        T["games"] += 1
        T["elims"] += len(ks); T["elims_combat"] += ks.count("combat")
        if ks:
            T["final_" + ks[-1]] += 1
print(dict(T))
