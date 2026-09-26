"""Stricter execution test on the product's converted instances: per turn at/after
assembly, count ACTIVATED (not triggered/cast) stack items by the seat whose object
is a line piece. Uses the same merged groups as verify_fired.py."""
import json, collections, re, sys
sys.path.insert(0, ".")
import verify_fired as V
import analysis, cards
from pathlib import Path
d = json.load(open("out.json"))
want = collections.defaultdict(list)
for c in d["conv"]:
    want[(c["arm"], c["pod"])].append(c)
ACT = re.compile(r"^(Ai\(\d+\)-\S+) activated (.+?)(?: targeting .*)?$")
res = []
for arm, pod, files in V.groups():
    cs = want.get((arm, pod))
    if not cs:
        continue
    result, _ = V.load_group(files)
    for c in cs:
        g = result["games"][c["n"] - 1]
        key = next(k for k in g["players"] if analysis._bare(k) == c["deck"])
        pieces = {analysis._norm(p) for p in c["line"].split(" + ")}
        per = collections.Counter()
        for t in g["turns"]:
            if t["turn"] < c["assembled_turn"]:
                continue
            for e in t["events"]:
                if e.get("action") != "stack_add":
                    continue
                m = ACT.match(e.get("raw", ""))
                if m and m.group(1) == key and cards.normalize_name(m.group(2)).lower() in pieces:
                    per[t["turn"]] += 1
        c["max_act_turn"] = max(per.values()) if per else 0
        res.append(c)
def strict(c): return c["method"] == "spell" or c["max_act_turn"] >= 5
print("converted instances:", len(res), "strict evidence:", sum(strict(c) for c in res),
      "none:", sum(not strict(c) for c in res))
fast = [c for c in res if c["own_turns_after"] <= 1]
print("won within 1 own turn of assembly:", len(fast))
print("strict OR within-1-own-turn:", sum(1 for c in res if strict(c) or c["own_turns_after"] <= 1))
by = collections.defaultdict(list)
for c in res: by[(c["arm"], c["pod"], c["deck"], c["line"])].append(c)
fired = [r for r in d["rows"] if r["reading"] == "fired"]
print("fired readings:", len(fired),
      "; no converted game with strict evidence:", sum(1 for r in fired if not any(strict(c) for c in by[(r['arm'], r['pod'], r['deck'], r['line'])])),
      "; no strict evidence and no win within 1 own turn:", sum(1 for r in fired if not any(strict(c) or c['own_turns_after'] <= 1 for c in by[(r['arm'], r['pod'], r['deck'], r['line'])])))
seat = collections.defaultdict(bool)
for c in res:
    k = (c["arm"], c["pod"], c["n"], c["deck"]); seat[k] = seat[k] or strict(c)
print("seat-games converted:", len(seat), "with no strict evidence on any line:", sum(1 for v in seat.values() if not v))
