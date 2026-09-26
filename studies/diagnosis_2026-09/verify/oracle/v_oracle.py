"""Independent re-count: every Demonic Consultation / Tainted Pact cast, its
timing relative to the caster's own Thassa's Oracle ETB trigger (LIFO over
open Oracle triggers), and the caster's fate. Also Oracle wins by seat type and
round (= TURN number / players)."""
import collections, glob, json, os, re, statistics, sys

S = "C:/Users/Vatto/Magic Rules Engine/studies/"
SETS = {
    "av_015_default": "agent_viability/runs_015_default/cell_*.jsonl",
    "av_winmax": "agent_viability/runs_winmax/cell_*.jsonl",
    "av_016_engine": "agent_viability/runs_016_engine/cell_*.jsonl",
    "br_agent_shipping": "behavior_rubric/runs_agent_shipping/*.jsonl",
    "tt_stage2": "tutor_targeting/runs_stage2/*.jsonl",
    "hc_stock": "human_ceiling/runs/*.jsonl",
    "br_agent_093": "behavior_rubric/runs_agent_093/*.jsonl",
    "br_agent_080": "behavior_rubric/runs_agent/*.jsonl",
}
EXTRA = {
    "tt_runs": "tutor_targeting/runs/*.jsonl",
    "tt_stage1": "tutor_targeting/runs_stage1/*.jsonl",
    "tt_stock": "tutor_targeting/runs_stock/*.jsonl",
}
if "--extra" in sys.argv:
    SETS.update(EXTRA)
P = r"(Ai\(\d\)-\S+)"
casts = collections.Counter()
casts_by_arm = collections.Counter()
examples = collections.defaultdict(list)
wins = []  # (arm, seat_type, method, round)
oracle_combo_cast = collections.Counter()
shim_versions = collections.Counter()
for arm, pat in SETS.items():
    for f in sorted(glob.glob(S + pat)):
        meta = None
        games = collections.defaultdict(list)
        agentrecs = collections.defaultdict(list)
        for l in open(f, encoding="utf-8"):
            try:
                r = json.loads(l)
            except Exception:
                continue
            rec = r.get("rec")
            if rec == "meta":
                meta = r
            elif rec == "entry":
                games[r["game"]].append(r)
            elif rec == "agent":
                agentrecs[r.get("game")].append(r)
        if not meta:
            continue
        shim_versions[(arm, meta.get("shim"))] += 1
        agents = dict(zip(meta["players"], meta["agents"]))
        nplayers = len(meta["players"])
        for g, es in games.items():
            for a in agentrecs.get(g, []):
                if a["event"] == "combo_cast" and "Thassa's Oracle" in a["detail"]:
                    oracle_combo_cast[(arm, a["detail"])] += 1
            es.sort(key=lambda r: r["seq"])
            outcome = {}
            turn = 0
            lastturn = 0
            for e in es:
                if e["type"] == "TURN":
                    m = re.match(r"Turn (\d+)", e["message"])
                    if m:
                        lastturn = int(m.group(1))
                if e["type"] == "GAME_OUTCOME":
                    m = re.match(P + r" has (won|lost) (.*)", e["message"])
                    if m:
                        outcome.setdefault(m.group(1), (m.group(2), m.group(3)))
            for p, (wl, how) in outcome.items():
                if wl == "won":
                    method = "oracle" if "Thassa" in how else "other"
                    wins.append((arm, agents.get(p), method, lastturn / nplayers, f, g))
            open_trig = []  # LIFO of players with an unresolved Oracle ETB trigger
            resolved = collections.Counter()
            oracle_on_bf_turn = {}
            cur_turn = 0
            for e in es:
                m = e["message"]
                if e["type"] == "TURN":
                    mm = re.match(r"Turn (\d+)", m)
                    if mm:
                        cur_turn = int(mm.group(1))
                mt = re.match(P + r" triggered Thassa's Oracle", m)
                if mt and e["type"] == "STACK_ADD":
                    open_trig.append(mt.group(1))
                    continue
                if e["type"] == "STACK_RESOLVE" and m.startswith("When Thassa's Oracle enters"):
                    if open_trig:
                        resolved[open_trig.pop()] += 1
                    continue
                mc = re.match(P + r" cast (.+?)(?: targeting .*)?$", m)
                if not mc or e["type"] != "STACK_ADD":
                    continue
                p, card = mc.group(1), mc.group(2)
                if card not in ("Demonic Consultation", "Tainted Pact"):
                    continue
                if p in open_trig:
                    state = "resp"
                elif resolved[p]:
                    state = "after"
                else:
                    state = "none"
                wl, how = outcome.get(p, ("unfinished", ""))
                if wl == "won":
                    fate = "won_oracle" if "Thassa" in how else "won_other"
                elif "empty library" in how:
                    fate = "decked"
                elif wl == "lost":
                    fate = "lost_other"
                else:
                    fate = "unfinished"
                k = (agents.get(p), card, state, fate)
                casts[k] += 1
                casts_by_arm[(arm, agents.get(p), card)] += 1
                if len(examples[k]) < 6:
                    examples[k].append(f"{arm} {os.path.basename(f)} g{g} {p} seq{e['seq']} t{cur_turn}")

print("shim versions:", dict(shim_versions))
print("\n== Consultation/Pact casts (seat, card, state, fate)")
for k, v in sorted(casts.items()):
    print(f"{v:4d}  {k}")
tot = collections.Counter()
for (seat, card, state, fate), v in casts.items():
    tot[(seat, card)] += v
    tot[(seat, card, state)] += v
    tot[(seat, card, "fate", fate)] += v
print("\n== totals")
for k, v in sorted(tot.items()):
    print(f"{v:4d}  {k}")
print("\n== by arm")
for k, v in sorted(casts_by_arm.items()):
    print(f"{v:4d}  {k}")
print("\n== wins")
wc = collections.Counter((w[1], w[2]) for w in wins)
print(dict(wc))
orw = [w[3] for w in wins if w[2] == "oracle"]
oth = [w[3] for w in wins if w[2] == "other"]
print("oracle wins n=%d median round %.2f range %.2f-%.2f" % (len(orw), statistics.median(orw), min(orw), max(orw)))
print("other wins n=%d median round %.2f" % (len(oth), statistics.median(oth)))
othplan = [w[3] for w in wins if w[2] == "other" and w[1] == "plan"]
othstock = [w[3] for w in wins if w[2] == "other" and w[1] == "stock"]
print("other wins plan n=%d median %.2f; stock n=%d median %.2f" % (len(othplan), statistics.median(othplan), len(othstock), statistics.median(othstock)))
print("oracle wins by arm:", collections.Counter((w[0], w[1]) for w in wins if w[2] == "oracle"))
print("\n== Oracle combo_cast details")
for k, v in sorted(oracle_combo_cast.items()):
    print(f"{v:4d}  {k}")
print("\n== examples")
for k, v in sorted(examples.items()):
    if k[0] == "plan":
        print(k)
        for x in v:
            print("     ", x)
