# When do seats cast their nonland tutors? Own-turn round of each cast (a cast on an opponent's turn
# is assigned the caster's current round). Also: share of tutors drawn that are never cast.
import os, json, glob, re, collections, sys, statistics
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
TURN = re.compile(r"^Turn (\d+) \((Ai\(\d\)-.+)\)$")
CAST = re.compile(r"^(Ai\(\d\)-.+?) cast (.+?)(?: targeting.*)?$")
def strip(n): return re.sub(r"^Ai\(\d\)-", "", n)
TUT = {}
for pf in glob.glob(os.path.join(ROOT, "behavior_rubric", "plans_*.json")):
    for deck, plan in json.load(open(pf))["decks"].items():
        TUT.setdefault(deck, set(plan.get("tutors", [])) - {"Magda, Brazen Outlaw"})
for d in sys.argv[1:]:
    rounds = collections.defaultdict(list); drawn = collections.Counter(); cast = collections.Counter()
    for p in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
        agents = {}; own = collections.Counter(); g_cur = None
        inhand = collections.defaultdict(set)
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"rec":"meta"'):
                    m = json.loads(line); agents = dict(zip(m["players"], m.get("agents") or ["stock"]*4))
                elif line.startswith('{"rec":"entry"') and ('"TURN"' in line or '"STACK_ADD"' in line):
                    e = json.loads(line)
                    if e["game"] != g_cur: g_cur = e["game"]; own = collections.Counter()
                    if e["type"] == "TURN":
                        mm = TURN.match(e["message"])
                        if mm: own[mm.group(2)] += 1
                    else:
                        mm = CAST.match(e["message"])
                        if mm:
                            pl, card = mm.group(1), e.get("card") or mm.group(2)
                            if card in TUT.get(strip(pl), ()):
                                pil = agents.get(pl, "stock")
                                rounds[pil].append(max(1, own[pl]))
                                cast[(pil)] += 1
                elif line.startswith('{"rec":"zone"'):
                    z = json.loads(line)
                    if z["to"] == "Hand" and z["from"] == "Library":
                        pl = z.get("toPlayer")
                        if pl and z["card"] in TUT.get(strip(pl), ()):
                            drawn[agents.get(pl, "stock")] += 1
    out = []
    for pil, v in sorted(rounds.items()):
        out.append(f"{pil}: tutorCasts={len(v)} drawnToHand={drawn[pil]} castRate~{100*len(v)/max(1,drawn[pil]):.0f}% median round={statistics.median(v)} rounds1-3={100*sum(1 for x in v if x<=3)/len(v):.0f}%")
    print(f"{d:40s}", " | ".join(out))
