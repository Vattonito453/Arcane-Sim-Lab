"""What do sim searches fetch? Category of the taken card, per seat type and
decider, with the strict win-line definition (Spellbook 'produces' names a
win: win the game / damage / life loss / opponent mill / infinite combat or
power), vs non-win line piece, vs value-8 finisher-regex false positive,
ramp, interaction, land, other."""
import json, re, sys, collections
from pathlib import Path
HERE = Path(__file__).parent
ROOT = Path(r"C:/Users/Vatto/Magic Rules Engine")
cache = json.loads((ROOT / "engine/card_cache.json").read_text(encoding="utf-8"))
WIN = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|each opponent loses|(?<!self-)(?<!self )mill\b|infinite combat phases|infinitely large creature|infinitely powerful|infinite power", re.I)
MANA = re.compile(r"add \{|add one mana|add two mana", re.I)
INTER = re.compile(r"counter target|destroy target|exile target|hexproof|indestructible|protection from|can't cast|can't be countered|each opponent sacrifices|return target .* to its owner's hand", re.I)
FIN = re.compile(r"wins? the game|loses? the game|combat damage to a player|infect|damage can't be prevented", re.I)

def fact(n):
    k = (n or "").lower()
    return cache.get(k) or cache.get(k.split(" // ")[0]) or {}

def load_plans(path):
    p = json.load(open(path, encoding="utf-8")); return p.get("decks", p)

def cat(name, plan):
    lines = plan.get("lines", [])
    if any(name in l["cards"] and WIN.search(" ; ".join(l.get("produces", []))) for l in lines):
        return "win-line piece"
    if any(name in l["cards"] for l in lines):
        return "non-win line piece"
    f = fact(name)
    text, tl = f.get("oracle_text") or "", f.get("type_line") or ""
    if "Land" in tl and "Creature" not in tl:
        return "land"
    if plan.get("search", {}).get("targets", {}).get(name) == 8 and FIN.search(text):
        return "finisher-regex (value 8, not a line)"
    if MANA.search(text) and (f.get("cmc") or 0) <= 3:
        return "ramp"
    if INTER.search(text):
        return "interaction"
    if not f:
        return "unknown-card"
    return "other/value"

def main(arms):
    for arm, plan_src in arms:
        d = json.load(open(HERE / f"v2_{arm}.json"))
        S = d["searches"]
        plan_cache = {}
        def plan_for(s):
            if plan_src == "auto":
                m = re.search(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)", s["file"])
                base = {"av015": "agent_viability/runs_015_default", "avwinmax": "agent_viability/runs_winmax",
                        "av016": "agent_viability/runs_016_engine", "rubric_ship": "behavior_rubric/runs_agent_shipping/plans"}[arm]
                pth = ROOT / "studies" / base / f"plans_{m.group(1)}.json"
            else:
                pth = Path(plan_src)
            if pth not in plan_cache:
                plan_cache[pth] = load_plans(pth)
            return plan_cache[pth].get(s["deck"], {})
        print(f"\n=== {arm}")
        groups = collections.defaultdict(collections.Counter)
        for s in S:
            tk = s.get("taken")
            if not tk or tk == "-":
                continue
            ag = s.get("agent")
            if ag == "plan":
                st = s.get("steer")
                key = "plan seat, shim steered (" + st["mode"] + ")" if st else "plan seat, stock pick stood"
            else:
                key = "stock seat"
            c = cat(tk, plan_for(s))
            groups[key][c] += 1
            groups[key + " [rounds1-4]" if s["round"] <= 4 else key + " [round5+]"][c] += 1
        order = ["win-line piece", "non-win line piece", "finisher-regex (value 8, not a line)", "ramp", "interaction", "land", "other/value", "unknown-card"]
        for k in sorted(groups):
            n = sum(groups[k].values())
            print(f"  {k:48s} n={n:4d}  " + "  ".join(f"{o.split(' ')[0]}={100*groups[k][o]/n:.0f}%" for o in order if groups[k][o]))

if __name__ == "__main__":
    S = str(ROOT / "studies")
    main([("av015", "auto"), ("avwinmax", "auto"), ("av016", "auto"), ("rubric_ship", "auto"),
          ("tt_stock", S + "/tutor_targeting/runs_stage1/plans_20260825_105436_pid22904.json"),
          ("tt_stage2", S + "/tutor_targeting/runs_stage2/plans_20260825_175454_pid81260.json")])
