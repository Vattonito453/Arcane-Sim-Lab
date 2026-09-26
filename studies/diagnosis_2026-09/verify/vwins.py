"""For every seat-game with an assembled line: what happened on the seat's winning
turn (if it won) and, for Oracle+Consultation assemblies that did not win, the
sequence of Oracle / Consultation events."""
import collections, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIES = r"C:/Users/Vatto/Magic Rules Engine/studies"
rows = json.load(open(os.path.join(HERE, "vrows.json")))
TURN_RE = re.compile(r"^Turn (\d+) \((.+)\)$")
ACT_RE = re.compile(r"^(Ai\(\d\)-\S+) (activated|triggered|cast) (.+?)(?: targeting .*)?$")

need = collections.defaultdict(list)
for r in rows:
    if r["assembled"] is not None:
        need[r["file"]].append(r)


def entries(f, games):
    per = collections.defaultdict(list)
    with open(os.path.join(STUDIES, f), encoding="utf-8") as fh:
        for line in fh:
            if '"rec":"entry"' in line or '"rec":"agent"' in line:
                r = json.loads(line)
                if r.get("game") in games:
                    per[r["game"]].append(r)
    return per


res = collections.Counter()
oracle_fail = []
plan_conv_detail = []
for f, rs in need.items():
    per = entries(f, {r["game"] for r in rs})
    for r in rs:
        ents = per[r["game"]]
        p = r["seat"]
        pieces = set(x for ln in r["asm_lines"] for x in ln.split(" + "))
        turn = 0
        it = collections.Counter()
        atk = collections.Counter()
        seqlog = []
        ag = []
        for e in ents:
            if e.get("rec") == "agent":
                if e.get("player") == p and e.get("event") in ("combo_cast", "combo_hold", "tutor_cast"):
                    ag.append((e.get("turn"), e["event"], e.get("detail", "")[:80]))
                continue
            if e["type"] == "TURN":
                m = TURN_RE.match(e["message"])
                if m:
                    turn = int(m.group(1))
            elif e["type"] == "STACK_ADD":
                m = ACT_RE.match(e["message"])
                if m and m.group(1) == p:
                    card = e.get("card") or m.group(3)
                    if card in pieces and m.group(2) in ("activated", "triggered"):
                        it[(turn, card)] += 1
                    if card in ("Thassa's Oracle", "Demonic Consultation", "Tainted Pact"):
                        seqlog.append((turn, m.group(2), card, e["message"][len(p) + 1:][:90]))
            elif e["type"] == "PHASE" and e["message"].startswith(p) and "Declare Attackers Step" in e["message"]:
                atk[turn] += 1
            elif e["type"] == "STACK_RESOLVE" and e.get("card") in ("Thassa's Oracle", "Demonic Consultation"):
                seqlog.append((turn, "resolve", e.get("card"), e["message"][:90]))
        grp = r["agent"]
        if r["won"]:
            wt = r["final"]
            win_iter = max([n for (t, c), n in it.items() if t == wt] or [0])
            if r["spell_win"]:
                kind = "spell"
            elif atk.get(wt, 0) >= 3:
                kind = "multi_combat_winturn"
            elif win_iter >= 5:
                kind = "loop_iter>=5_winturn"
            else:
                kind = "plain"
            win_cls = "conv2" if r["converted"] else "late"
            res[(grp, win_cls, kind)] += 1
            if grp == "plan" and r["converted"] and not r["spell_win"]:
                plan_conv_detail.append((f.split("/")[1], os.path.basename(f)[5:-6], r["game"], p.split("-", 1)[1],
                                         r["asm_lines"][:2], "asm", r["assembled"], "win", wt,
                                         "atk", atk.get(wt, 0), "iter", win_iter))
        if any("Consultation" in ln or "Tainted Pact" in ln for ln in r["asm_lines"]) and not r["spell_win"]:
            oracle_fail.append((grp, f.split("/")[1], os.path.basename(f)[5:-6], r["game"], p, r["assembled"], r["won"], seqlog[:10], ag[:6]))

for k in sorted(res):
    print(k, res[k])
print("\n== plan converted, non-spell")
for x in plan_conv_detail:
    print("  ", x)
print("\n== Oracle-line assemblies without an Oracle win:", len(oracle_fail))
for x in oracle_fail:
    print("  ", x[:7])
    for s in x[7]:
        print("        ", s)
    for s in x[8]:
        print("        agent", s)
