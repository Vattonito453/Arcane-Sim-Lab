"""Every Demonic Consultation / Tainted Pact cast and every Thassa's Oracle cast,
classified by what the Oracle's ETB trigger was doing at that moment (entry
seq order inside a game's log block), plus the caster's fate."""
import collections, glob, json, os, re

S = r"C:/Users/Vatto/Magic Rules Engine/studies/"
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
DIG = ("Demonic Consultation", "Tainted Pact")
res = collections.Counter()
ex = collections.defaultdict(list)
oracle_casts = collections.Counter()
for arm, pat in SETS.items():
    for f in sorted(glob.glob(S + pat)):
        meta = None
        games = collections.defaultdict(list)
        for l in open(f, encoding="utf-8"):
            try:
                r = json.loads(l)
            except Exception:
                continue
            if r.get("rec") == "meta":
                meta = r
            elif r.get("rec") == "entry":
                games[r["game"]].append(r)
        if not meta:
            continue
        agents = dict(zip(meta["players"], meta["agents"]))
        for g, es in games.items():
            es.sort(key=lambda r: r["seq"])
            outcome = {}
            for e in es:
                if e["type"] == "GAME_OUTCOME":
                    m = re.match(r"(Ai\(\d\)-\S+) has (won|lost) (.*)", e["message"])
                    if m:
                        outcome[m.group(1)] = m.group(2) + " " + m.group(3)[:60]
            trig_open = {}  # player -> True while an Oracle ETB trigger is on the stack
            oracle_resolved = collections.Counter()
            for e in es:
                m = e["message"]
                mt = re.match(r"(Ai\(\d\)-\S+) triggered Thassa's Oracle", m)
                if mt:
                    trig_open[mt.group(1)] = True
                if e["type"] == "STACK_RESOLVE" and m.startswith("When Thassa's Oracle enters"):
                    for p in list(trig_open):
                        if trig_open[p]:
                            trig_open[p] = False
                            oracle_resolved[p] += 1
                            break
                mc = re.match(r"(Ai\(\d\)-\S+) cast (.+?)(?: targeting .*)?$", m)
                if not mc:
                    continue
                p, card = mc.group(1), mc.group(2)
                if card == "Thassa's Oracle":
                    oracle_casts[(agents.get(p), "oracle cast with Consult/Pact line?")] += 0
                if card not in DIG:
                    continue
                if trig_open.get(p):
                    state = "in response to Oracle ETB trigger"
                elif oracle_resolved[p] > 0:
                    state = "AFTER Oracle trigger already resolved"
                else:
                    state = "no Oracle trigger this game yet"
                fate = outcome.get(p, "unfinished")
                fate_k = ("WON via Oracle" if "Thassa" in fate and fate.startswith("won") else
                          "decked (empty library)" if "empty library" in fate else
                          "won other" if fate.startswith("won") else "lost other")
                k = (agents.get(p), card, state, fate_k)
                res[k] += 1
                if len(ex[k]) < 4:
                    ex[k].append(f"{arm} {os.path.basename(f)} g{g} {p} seq{e['seq']}")
for k, v in sorted(res.items(), key=lambda kv: (kv[0][0], -kv[1])):
    print(f"{v:4d}  {k}")
print()
for k, v in ex.items():
    if k[0] == "plan" and k[2] != "no Oracle trigger this game yet":
        print(k)
        for x in v:
            print("     ", x)
