"""Reconstruct the shim's line-of-sight gate from zone records.

For each plan seat, at the END of each of its own turns, replay hand/board/
command and ask: was a plan tutor in hand (held through the turn)? What was
the best line's distance (pieces outside hand+board+command)? Which branch
of comboPriority's tutor path could fire?

  owned0   a line with 0 outside exists (not fully on board): lineOfSight
           returns it, missingOutside == null, tutor_cast CANNOT fire
  short1   best line is exactly 1 outside, tutor in hand: tutor_cast ELIGIBLE
  short2   best line is 2 outside: gate closed (the 'opener' case)
  short3+  3+ outside or every line fully assembled / no lines
Also counts tutor_cast events, and how often the tutor_cast search could even
offer the missing piece (comboPick=yes).
Usage: py gate_state.py <arm> <plans|auto> <glob>...
"""
import json, re, sys, glob, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from parse2 import load_plans, POD_RE, TUTORS

def analyse(fn, plans, out):
    games = collections.defaultdict(lambda: {"zones": [], "entries": [], "agent": [], "result": None})
    meta = None
    for line in open(fn, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        rec = r.get("rec")
        if rec == "meta":
            meta = r; continue
        g = r.get("game")
        if rec == "zone": games[g]["zones"].append(r)
        elif rec == "entry" and r["type"] == "TURN": games[g]["entries"].append(r)
        elif rec == "agent": games[g]["agent"].append(r)
        elif rec == "result": games[g]["result"] = r
    players = meta["players"]
    agents = dict(zip(players, meta["agents"]))
    for gi, G in games.items():
        if G["result"] is None:
            continue
        whose = {}
        for e in G["entries"]:
            m = re.match(r"Turn (\d+) \((.+)\)", e["message"])
            if m: whose[int(m.group(1))] = m.group(2)
        maxturn = max(whose) if whose else 0
        zone = {}   # cid -> (zone, controller, name)
        Z = G["zones"]
        zi = 0
        tc_by = collections.Counter((a["player"], a["turn"]) for a in G["agent"] if a["event"] == "tutor_cast")
        for t in range(0, maxturn + 1):
            while zi < len(Z) and (Z[zi].get("turn") or 0) <= t:
                z = Z[zi]
                ctl = z.get("toPlayer") or z.get("fromPlayer")
                zone[z["cardId"]] = (z["to"], ctl, z["card"])
                zi += 1
            p = whose.get(t)
            if p is None or agents.get(p) != "plan":
                continue
            plan = plans.get(re.sub(r"^Ai\(\d+\)-", "", p), {})
            lines = [set(l["cards"]) for l in plan.get("lines", [])]
            ptut = set(plan.get("tutors", []))
            H, B, C = set(), set(), set()
            for cid, (zn, ctl, nm) in zone.items():
                if ctl != p: continue
                if zn == "Hand": H.add(nm)
                elif zn == "Battlefield": B.add(nm)
                elif zn == "Command": C.add(nm)
            held_plan = sorted(H & ptut)
            held_broad = sorted(H & TUTORS)
            if not held_broad:
                continue
            best = None
            n_owned0 = 0
            for L in lines:
                if L <= B:
                    continue
                outside = len(L - B - H - C)
                if best is None or outside < best:
                    best = outside
            if not lines:
                state = "no-lines"
            elif best is None:
                state = "all-assembled"
            elif best == 0:
                state = "owned0"
            elif best == 1:
                state = "short1"
            elif best == 2:
                state = "short2"
            else:
                state = "short3+"
            out.append({"file": Path(fn).name, "game": gi, "turn": t, "round": (t - 1) // len(players) + 1,
                        "player": p, "held_plan": held_plan, "held_broad": held_broad,
                        "held_nonplan": sorted(set(held_broad) - ptut), "state": state,
                        "lands": sum(1 for cid, (zn, ctl, nm) in zone.items() if ctl == p and zn == "Battlefield"),
                        "tutor_cast_this_turn": tc_by.get((p, t), 0)})

def main():
    arm, pa0 = sys.argv[1], sys.argv[2]
    files = []
    for g in sys.argv[3:]:
        files += sorted(glob.glob(g))
    out = []
    for fn in files:
        pa = pa0
        if pa == "auto":
            d = Path(fn).parent; m = POD_RE.search(Path(fn).name); cand = []
            if m:
                for base in (d, d / "plans", d.parent):
                    cand += list(base.glob(f"plans_{m.group(1)}.json"))
            pa = str(cand[0]) if cand else "none"
        analyse(fn, load_plans(pa), out)
    json.dump(out, open(Path(__file__).parent / f"gate_{arm}.json", "w"))
    held = [o for o in out if o["held_plan"]]
    st = collections.Counter(o["state"] for o in held)
    print(f"{arm}: own turns ending with a plan.tutor still in hand = {len(held)}")
    for k, v in st.most_common():
        print(f"   {k:14s} {v:4d} ({100*v/len(held):.0f}%)")
    r14 = [o for o in held if o["round"] <= 4]
    st2 = collections.Counter(o["state"] for o in r14)
    print(f"   rounds 1-4 only: {len(r14)} ->", dict(st2.most_common()))
    nonplan = [o for o in out if o["held_nonplan"]]
    print(f"   own turns ending with a tutor the plan does NOT list: {len(nonplan)}",
          collections.Counter(n for o in nonplan for n in o["held_nonplan"]).most_common(8))

if __name__ == "__main__":
    main()
