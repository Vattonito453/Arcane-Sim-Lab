import json, glob, re, collections, os
ROOT = "C:/Users/Vatto/Magic Rules Engine/studies/"
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
# resource -> outlet cards that turn it into a win (conservative, well-known cEDH finishes)
MANA_OUT = {"Thrasios, Triton Hero", "Finale of Devastation", "Walking Ballista", "Staff of Domination", "Aetherflux Reservoir", "Blue Sun's Zenith", "Stroke of Genius"}
STORM_OUT = {"Brain Freeze", "Grapeshot", "Aetherflux Reservoir"}
DRAW_OUT = {"Thassa's Oracle", "Laboratory Maniac", "Jace, Wielder of Mysteries"}
def classify(line, cards):
    s = " ; ".join(line.get("produces", []))
    if WIN.search(s): return "strict-win"
    if re.search(r"tokens with haste", s, re.I): return "haste-tokens(win)"
    if re.search(r"Put all artifact cards", s) and "Grinding Station" in cards: return "library-dump+GrindingStation"
    outs = set()
    if re.search(r"mana", s, re.I): outs |= MANA_OUT & cards
    if re.search(r"storm count", s, re.I): outs |= STORM_OUT & cards
    if re.search(r"self-mill|Exile your library|card draw|draw triggers", s, re.I): outs |= DRAW_OUT & cards
    outs -= set(line["cards"])
    if outs: return "outlet-in-deck"
    return "no-known-outlet"
def load(pattern):
    P = {}
    for f in sorted(glob.glob(pattern)):
        pod = re.search(r"plans_(.+)\.json", f).group(1)
        P[pod] = json.load(open(f, encoding="utf-8"))["decks"]
    return P
P = load(ROOT + "behavior_rubric/plans_*.json")
tot = collections.Counter(); per = collections.defaultdict(collections.Counter)
for pod, decks in P.items():
    for dn, p in decks.items():
        cards = set(p.get("roles", {}).keys())
        for l in p.get("lines", []):
            c = classify(l, cards); tot[c] += 1; per[dn][c] += 1
n = sum(tot.values())
print("lines", n, {k: f"{v} ({100*v/n:.0f}%)" for k, v in tot.most_common()})
for dn in ["derevi","nadu","dexter_kinnan","isaac_yisan","matt_sisay","kinnan","natalie_magda","magda","rog_ishai","selvala_archetype"]:
    print("  ", dn, dict(per[dn]))
# steer targets reclassified
ARMS = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping"}
POD = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")
ORDER = ["strict-win","haste-tokens(win)","library-dump+GrindingStation","outlet-in-deck","no-known-outlet"]
for arm, d in ARMS.items():
    PP = load(ROOT + d + "/plans_*.json") or load(ROOT + d + "/plans/plans_*.json")
    C = collections.defaultdict(collections.Counter)
    for f in sorted(glob.glob(ROOT + d + "/*.jsonl")):
        m = POD.search(os.path.basename(f))
        if not m: continue
        decks = PP[m.group(1)]
        for line in open(f, encoding="utf-8"):
            if '"tutor_steer"' not in line: continue
            r = json.loads(line)
            deck = r["player"].split("-", 1)[1]; p = decks.get(deck, {}); cards = set(p.get("roles", {}).keys())
            det = r["detail"]; mode = re.search(r"mode=(\w+)", det).group(1); card = re.search(r"steer=(.+?) over=", det).group(1)
            cls = [classify(l, cards) for l in p.get("lines", []) if card in l["cards"]]
            if not cls: best = "notline"
            else: best = min(cls, key=ORDER.index)
            C[mode][best] += 1
    for mode, cc in sorted(C.items()):
        k = sum(cc.values())
        print(f"{arm:12s} {mode:6s} n={k:4d} " + "  ".join(f"{o}={cc[o]}({100*cc[o]/k:.0f}%)" for o in ORDER + ["notline"] if cc[o]))
