"""Loop evidence for assembled seat-games: how often did line pieces actually
iterate after assembly, and did Godo+Helm conversions run extra combats?"""
import collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIES = r"C:/Users/Vatto/Magic Rules Engine/studies"
rows = json.load(open(os.path.join(HERE, "vrows.json")))
TURN_RE = re.compile(r"^Turn (\d+) \((.+)\)$")
ACT_RE = re.compile(r"^(Ai\(\d\)-\S+) (activated|triggered|cast) (.+?)(?: targeting .*)?$")

need = collections.defaultdict(list)
for r in rows:
    if r["assembled"] is not None:
        need[(r["file"], r["game"])].append(r)

cache = {}
for (f, g), rs in need.items():
    pass

by_file = collections.defaultdict(set)
for (f, g) in need:
    by_file[f].add(g)

stats = {}
for f, gs in by_file.items():
    per_game = collections.defaultdict(list)
    with open(os.path.join(STUDIES, f), encoding="utf-8") as fh:
        for line in fh:
            if '"rec":"entry"' not in line:
                continue
            r = json.loads(line)
            if r.get("game") in gs:
                per_game[r["game"]].append(r)
    for g, ents in per_game.items():
        turn = 0
        owner = {}
        cnt = collections.Counter()      # (player, turn, card, verb)
        atk_steps = collections.Counter()  # turn -> declare attackers steps
        for e in ents:
            if e["type"] == "TURN":
                m = TURN_RE.match(e["message"])
                if m:
                    turn = int(m.group(1)); owner[turn] = m.group(2)
            elif e["type"] == "STACK_ADD":
                m = ACT_RE.match(e["message"])
                if m:
                    cnt[(m.group(1), turn, e.get("card") or m.group(3), m.group(2))] += 1
            elif e["type"] == "PHASE" and "Declare Attackers Step" in e["message"]:
                atk_steps[turn] += 1
        stats[(f, g)] = (cnt, atk_steps, owner)

out = collections.defaultdict(collections.Counter)
examples = collections.defaultdict(list)
for (f, g), rs in need.items():
    cnt, atk, owner = stats[(f, g)]
    for r in rs:
        p = r["seat"]
        pieces = set()
        for ln in r["asm_lines"]:
            pieces.update(ln.split(" + "))
        best = 0
        for (pp, t, card, verb), n in cnt.items():
            if pp == p and card in pieces and t >= r["assembled"] and verb in ("activated", "triggered"):
                best = max(best, n)
        maxatk = max([atk[t] for t in atk if owner.get(t) == p and t >= r["assembled"]] or [0])
        grp = r["agent"]
        cls = ("conv" if r["converted"] else "noconv")
        bucket = "iter>=5" if best >= 5 else ("iter2-4" if best >= 2 else "iter<=1")
        out[(grp, cls)][bucket] += 1
        if maxatk >= 3:
            out[(grp, cls)]["multi_combat>=3"] += 1
        # Godo+helm detail
        if any("Godo" in x and "Helm" in x for x in r["conv_lines"]):
            wt = r["final"]
            out[(grp, "godo_conv")]["n"] += 1
            if r["helm_on_godo_turns"]:
                out[(grp, "godo_conv")]["helm_attached_to_godo"] += 1
            if atk.get(wt, 0) >= 2:
                out[(grp, "godo_conv")]["winturn_attack_steps>=2"] += 1
            examples[(grp, "godo")].append((f, g, p, wt, atk.get(wt, 0), r["helm_on_godo_turns"][:3]))
        if best >= 5 and not r["converted"]:
            examples[(grp, "iter_noconv")].append((f, g, p, r["asm_lines"][:2], best, r["won"]))

for k in sorted(out):
    print(k, dict(out[k]))
for k, v in examples.items():
    print("==", k, len(v))
    for x in v[:12]:
        print("   ", x)
