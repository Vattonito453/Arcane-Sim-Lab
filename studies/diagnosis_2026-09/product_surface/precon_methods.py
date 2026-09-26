import sys, json, glob, re, collections
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import shim_log_adapter, analysis
RE_LIFE = re.compile(r"^Life:\s*(.+?)\s+(-?\d+)\s*>\s*(-?\d+)")
def final_kind(g):
    flat = [e for t in g.get("turns") or [] for e in t.get("events") or []]
    kinds = []
    for i, e in enumerate(flat):
        if e.get("action") != "life_change": continue
        m = RE_LIFE.match(e.get("raw",""))
        if not (m and int(m.group(3)) <= 0 < int(m.group(2))): continue
        who = m.group(1).strip(); k = "noncombat"
        for j in range(i-1, max(-1, i-10), -1):
            rr = flat[j].get("raw","")
            if flat[j].get("action") == "damage" and rr.rstrip(".").endswith("to " + who):
                k = "combat" if " combat damage to " in rr else "noncombat"; break
            if flat[j].get("action") == "phase": break
        kinds.append(k)
    return kinds
M = collections.Counter(); K = collections.Counter()
for f in sorted(glob.glob(sys.argv[1])):
    r = shim_log_adapter.parse_shim_jsonl(open(f, encoding="utf-8", errors="replace").read(), source=f)
    for g in r.get("games") or []:
        wm = analysis.win_method(g)["method"]
        M[wm] += 1
        if wm == "combat damage / life loss":
            ks = final_kind(g)
            if ks:
                K["final_" + ks[-1]] += 1
                K["elims"] += len(ks); K["elims_combat"] += ks.count("combat")
print("methods:", dict(M)); print("under combat label:", dict(K))
