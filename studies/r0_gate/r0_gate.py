"""R0 gate (tasks/25-repair-plan.md, section 4.4): Richard's pod, 16 games on
shim 0.15.0 vs 16 on 0.16.0, same plans, all four seats plan agents as in
production. Pass: re-ask loop signature 0 on 0.16.0, no crashes, other
agent-event rates per seat-game within 2 SE.

    py r0_gate.py run      # 8 JVMs: 4 rotations x 4 games per arm
    py r0_gate.py report
"""
import collections, glob, json, math, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SP = HERE.parent
REPO = Path(r"C:/Users/Vatto/Magic Rules Engine")
FORGE = Path(r"C:/Users/Vatto/forge/forge-gui-desktop-2.0.13-jar-with-dependencies.jar")
JARS = {
    "0.15.0": Path(r"C:/Users/Vatto/simlab-forge-shim/simlab-forge-shim-0.15.0.jar"),
    "0.16.0": SP / "r0-shim-0.16.0-62fe295.jar",
}
DECKS = [SP / "richard/dck/kess_reanimator_305b76d7.dck",
         SP / "richard/dck/skrat_s_revenge_239c6293.dck",
         SP / "richard/dck/stella_lee_wild_card_79f6872f.dck",
         REPO / "engine/decks/krenko_goblins.dck"]
GAMES_PER_ROT = 4


def build_plans():
    out = HERE / "plans.json"
    if out.exists():
        return out
    os.environ["MTG_DATA_DIR"] = str(SP / "richard/cache")
    sys.path.insert(0, str(REPO / "engine"))
    from deck_plan import build_plans as bp
    plans = bp([str(d) for d in DECKS])
    out.write_text(json.dumps(plans), encoding="utf-8")
    return out


def cell(spec):
    arm, rot, plans = spec
    out = HERE / f"{arm}_rot{rot}.jsonl"
    if out.exists() and '"rec":"result"' in out.read_text(encoding="utf-8", errors="replace"):
        return f"{arm} rot{rot} cached"
    order = DECKS[rot:] + DECKS[:rot]
    cmd = ["java", "-Xmx3g", "-cp", f"{JARS[arm]}{os.pathsep}{FORGE}", "simlab.shim.SimShim",
           "--decks", *[str(d) for d in order], "--games", str(GAMES_PER_ROT),
           "--timeout", "900", "--max-turns", "120", "--plans", str(plans),
           "--seat-pilots", ",".join(["plan:SimLabHuman"] * 4), "--out", str(out)]
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        rc = subprocess.run(cmd, cwd=r"C:/Users/Vatto/forge", stdout=subprocess.DEVNULL,
                            stderr=eh, check=False).returncode
    return f"{arm} rot{rot} rc={rc}"


def run():
    plans = build_plans()
    specs = [(arm, rot, plans) for arm in JARS for rot in range(4)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(cell, specs):
            print(r, flush=True)


def report():
    rows = {}
    for arm in JARS:
        games = decided = timeouts = 0
        seat_games = 0
        ev = collections.Counter()
        per_turn = collections.Counter()
        crashes = 0
        shim = set()
        for rot in range(4):
            f = HERE / f"{arm}_rot{rot}.jsonl"
            if not f.exists():
                crashes += 1
                continue
            got = 0
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if '"rec":"meta"' in line:
                    shim.add(json.loads(line).get("shim"))
                elif '"rec":"result"' in line:
                    r = json.loads(line)
                    games += 1; got += 1; seat_games += 4
                    if r.get("timedOut"):
                        timeouts += 1
                    elif r.get("winner") and not r.get("draw"):
                        decided += 1
                elif '"rec":"agent"' in line:
                    r = json.loads(line)
                    ev[r["event"]] += 1
                    if r["event"] == "kingmaker_reaim":
                        per_turn[(rot, r["game"], r["turn"], r["player"])] += 1
            if got < GAMES_PER_ROT:
                crashes += 1
        loop_turns = sum(1 for v in per_turn.values() if v > 1)
        worst = max(per_turn.values()) if per_turn else 0
        rows[arm] = dict(shim=sorted(x for x in shim if x), games=games, decided=decided,
                         timeouts=timeouts, crashed_cells=crashes, seat_games=seat_games,
                         loop_turns=loop_turns, worst_reaims_in_a_turn=worst, events=ev)
    a, b = rows["0.15.0"], rows["0.16.0"]
    for arm, r in rows.items():
        print(f"{arm}: shim={r['shim']} games={r['games']} decided={r['decided']} timeouts={r['timeouts']} "
              f"crashed_cells={r['crashed_cells']} loop_turns(>1 reaim/turn)={r['loop_turns']} "
              f"worst={r['worst_reaims_in_a_turn']} attack_reask={r['events']['attack_reask']} "
              f"attack_reverted={r['events']['attack_reverted']}")
    print("\nper seat-game rates (0.15.0 vs 0.16.0), Poisson SE of the difference:")
    fails = []
    keys = sorted(set(a["events"]) | set(b["events"]))
    for k in keys:
        if k in ("attack_reask", "attack_reverted"):
            continue
        na, nb = a["events"][k], b["events"][k]
        ra, rb = na / max(1, a["seat_games"]), nb / max(1, b["seat_games"])
        se = math.sqrt(na / max(1, a["seat_games"]) ** 2 + nb / max(1, b["seat_games"]) ** 2) if (na + nb) else 0
        se = math.sqrt(na) / max(1, a["seat_games"]) if na else 0
        se = math.sqrt((math.sqrt(na) / max(1, a["seat_games"])) ** 2 + (math.sqrt(nb) / max(1, b["seat_games"])) ** 2)
        z = (rb - ra) / se if se else 0
        flag = "  <-- beyond 2 SE" if abs(z) > 2 else ""
        if abs(z) > 2:
            fails.append(k)
        print(f"  {k:22s} {ra:7.2f} {rb:7.2f}  z={z:+.2f}{flag}")
    ok = (b["loop_turns"] == 0 and a["crashed_cells"] == 0 and b["crashed_cells"] == 0)
    print(f"\nre-ask loop gone on 0.16.0: {b['loop_turns'] == 0}; crashes: {a['crashed_cells'] + b['crashed_cells']}; "
          f"rates beyond 2 SE: {fails or 'none'}")
    print("R0 GATE:", "PASS" if ok and not fails else "REVIEW (see above)")


if __name__ == "__main__":
    {"run": run, "report": report}[sys.argv[1]]()
