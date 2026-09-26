"""For every activation of a card whose Forge script is AI:RemoveDeck:All, was
the activated object the real card, or a copy (Sculpting Steel, Metamorph...)
whose own script is not flagged? Two passes per file: entries precede zones."""
import json, glob, re, collections, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from forge_cards import load, facts
idx = load()
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_*.jsonl", "agent_viability/runs_winmax/cell_*.jsonl",
        "agent_viability/runs_016_engine/cell_*.jsonl", "behavior_rubric/runs_agent_shipping/*.jsonl",
        "tutor_targeting/runs_stage2/*.jsonl", "human_ceiling/runs/*.jsonl",
        "behavior_rubric/runs_agent/*.jsonl", "behavior_rubric/runs_agent_093/*.jsonl"]
rem_cache = {}
def rem(name):
    if name not in rem_cache:
        f = facts(idx, name)
        rem_cache[name] = bool(f and f["remAll"])
    return rem_cache[name]
out = collections.Counter()
present = collections.Counter()
for pat in PATS:
    for f in glob.glob(S + pat):
        recs = [json.loads(l) for l in open(f, encoding="utf-8")]
        origin = {}   # (game, cardId) -> name the object had when it first entered a zone from Library/Hand
        for r in recs:
            if r.get("rec") == "zone":
                k = (r["game"], r["cardId"])
                if k not in origin and r["from"] in ("Library", "Hand", "Command", "None"):
                    origin[k] = r["card"]
                if r["to"] == "Battlefield" and rem(r["card"]):
                    present[(r["card"], "real" if origin.get(k) == r["card"] else "copy")] += 1
        for r in recs:
            if r.get("rec") == "entry" and r["type"] == "STACK_ADD":
                m = re.match(r"(Ai\(\d\)-\S+) activated (.+?)(?: targeting .*)?$", r["message"])
                if not m:
                    continue
                card = r.get("card") or m.group(2)
                if not rem(card):
                    continue
                o = origin.get((r["game"], r.get("cardId")))
                out[(card, "real card" if o == card else f"copy (object began as {o})")] += 1
print("activations of AI:RemoveDeck:All cards, by whether the object is the real card:")
for k, v in out.most_common():
    print(f"  {v:4d} {k}")
print("RemoveDeck:All cards entering the battlefield (real vs copy):")
for k, v in present.most_common(25):
    print(f"  {v:4d} {k}")
