#!/usr/bin/env python3
"""G0a analysis, committed with PREREG.md before any game ran.

    py studies/hotfix_g0/read_g0a.py            # prints the reading and the decision
    py studies/hotfix_g0/read_g0a.py --json out.json

Reads raw shim JSONL from $G0A_OUT/runs/<arm>/<bed>_rot<r>.jsonl (see run_g0a.py).
Every threshold below is quoted from PREREG.md; changing one after the run is a
protocol violation and must be reported as such.
"""
from __future__ import annotations

import argparse, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "engine"))
sys.path.insert(0, str(HERE))
import run_g0a as R  # noqa: E402  (paths, beds, arms: one definition)

SEAT = re.compile(r"^Ai\((\d+)\)-")
ORACLE = "won by spell 'Thassa's Oracle'"
ONLY_017 = {"tutor_skip"}          # events 0.16.0 cannot emit (excluded from E2)

# PREREG thresholds
P1_MAX = 0.05
P1_MIN_CASTS = 20
G1_MIN = 0.50
G2_MIN_SHARE = 0.70
G3_BAND = 0.25
G4_SE = 2.0
ALPHA = 0.05


def bare(p: str) -> str:
    return SEAT.sub("", p or "").strip()


def read_cell(path: Path) -> dict:
    """Games of one cell: players, result, agent-event counts, outcome lines."""
    meta, games = None, defaultdict(lambda: {"events": Counter(), "outcomes": []})
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rec = r.get("rec")
        if rec == "meta":
            meta = r
        elif rec == "result":
            games[r.get("game")]["result"] = r
        elif rec == "agent":
            games[r.get("game")]["events"][r.get("event")] += 1
        elif rec == "entry" and r.get("type") == "GAME_OUTCOME":
            games[r.get("game")]["outcomes"].append(r.get("message") or "")
    players = (meta or {}).get("players") or []
    done = [dict(g, players=players) for k, g in sorted(games.items(), key=lambda kv: (kv[0] is None, kv[0])) if "result" in g]
    return {"meta": meta, "games": done}


def load_arm(arm: str) -> dict:
    out = {"cells": {}, "games": []}
    for name, bed in R.beds().items():
        for rot in range(4):
            f = R.OUT / "runs" / arm / f"{name}_rot{rot}.jsonl"
            c = read_cell(f) if f.exists() else {"meta": None, "games": []}
            out["cells"][(name, rot)] = {"path": f, "want": bed["games"], "got": len(c["games"])}
            for g in c["games"]:
                g["bed"] = name
                out["games"].append(g)
    return out


def tutor_metrics(arm: str) -> dict:
    from qa import context as qctx, tutors
    per_bed = []
    version = R.ARMS[arm][1]
    for name, bed in R.beds().items():
        paths = sorted((R.OUT / "runs" / arm).glob(f"{name}_rot*.jsonl"))
        if not paths:
            continue
        cache = bed["cache"]
        facts = qctx.CardFacts.load(str(cache / "card_cache.json"))
        idx = sorted((cache / "forge_index").glob("*"))
        forge = qctx.load_forge_index(str(idx[-1])) if idx else None
        ctx = qctx.from_jsonl([str(p) for p in paths], plans=str(R.OUT / f"plans_{name}_v{version}.json"),
                              facts=facts, forge=forge)
        m, _ = tutors.detect(ctx)
        per_bed.append(m)
    return tutors.combine(per_bed) if len(per_bed) > 1 else per_bed[0]


def rates(games: list[dict]) -> dict[str, list[float]]:
    kinds = set()
    for g in games:
        kinds |= set(g["events"])
    return {k: [g["events"][k] / 4.0 for g in games] for k in sorted(kinds)}


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def clustered_z(a: list[float], b: list[float]) -> tuple[float, float]:
    """Difference of per-game means (b - a), with the game as the unit."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0, 1.0
    ma, mb = mean(a), mean(b)
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return 0.0, 1.0
    z = (mb - ma) / se
    p = math.erfc(abs(z) / math.sqrt(2))
    return z, p


def deck_wins(games: list[dict]) -> dict[str, tuple[int, int]]:
    """deck -> (wins, decided games it played)."""
    out = defaultdict(lambda: [0, 0])
    for g in games:
        r = g["result"]
        decided = bool(r.get("winner")) and not r.get("draw") and not r.get("timedOut")
        if not decided:
            continue
        m = SEAT.match(r.get("winner") or "")
        wseat = int(m.group(1)) if m else None
        for i, p in enumerate(g["players"]):
            d = bare(p)
            out[d][1] += 1
            if wseat == i + 1:
                out[d][0] += 1
    return {k: tuple(v) for k, v in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    arms = {k: load_arm(k) for k in R.ARMS}
    rep, verdict = {}, {}

    # E1: crashed or short cells
    short = {arm: [f"{b} rot{r}: {c['got']}/{c['want']}" for (b, r), c in d["cells"].items() if c["got"] < c["want"]]
             for arm, d in arms.items()}
    verdict["E1"] = not any(short.values())
    rep["E1_short_cells"] = short

    # Tutor metrics
    tm = {arm: tutor_metrics(arm) for arm in ("C", "T")}
    tp = tm["T"]["pooled"]
    cp = tm["C"]["pooled"]
    rep["tutors_T"] = {k: tp.get(k) for k in ("tutor_cast", "unreachable", "unreachable_rate", "restriction_excludes",
                                              "x_zero", "x_resolved", "failed_to_target", "gy_steers", "gy_steers_no_use",
                                              "gy_steers_graveyard_use", "casts_per_drawn", "closer_overrides",
                                              "tutor_skips", "tutor_skip_reasons", "unreachable_reasons")}
    rep["tutors_C"] = {k: cp.get(k) for k in rep["tutors_T"]}

    casts = tp.get("tutor_cast", 0) or 0
    unre = tp.get("unreachable", 0) or 0
    if casts < P1_MIN_CASTS:
        verdict["P1"] = None   # undecided: extend per PREREG
    else:
        verdict["P1"] = unre / casts <= P1_MAX
    verdict["P2"] = (tp.get("gy_steers_no_use", 0) or 0) == 0
    verdict["P3"] = (tp.get("x_zero", 0) or 0) == 0 and (tp.get("failed_to_target", 0) or 0) == 0
    cpd = tp.get("casts_per_drawn")
    verdict["G1"] = cpd is not None and cpd >= G1_MIN

    # G2: Oracle alternate wins
    orc = {arm: sum(1 for g in arms[arm]["games"] if any(ORACLE in o for o in g["outcomes"])) for arm in ("C", "T")}
    rep["G2_oracle_wins"] = orc
    verdict["G2"] = True if orc["C"] == 0 else orc["T"] >= G2_MIN_SHARE * orc["C"]

    # G3: counter_fire per seat-game
    cf = {arm: mean([g["events"]["counter_fire"] / 4.0 for g in arms[arm]["games"]]) for arm in ("C", "T")}
    rep["G3_counter_fire_per_seat_game"] = cf
    verdict["G3"] = True if cf["C"] == 0 else abs(cf["T"] - cf["C"]) <= G3_BAND * cf["C"]

    # G4: per-deck win share, T vs C
    wc, wt = deck_wins(arms["C"]["games"]), deck_wins(arms["T"]["games"])
    g4 = {}
    for d in sorted(set(wc) | set(wt)):
        (w1, n1), (w2, n2) = wc.get(d, (0, 0)), wt.get(d, (0, 0))
        if not n1 or not n2:
            g4[d] = {"C": f"{w1}/{n1}", "T": f"{w2}/{n2}", "fail": False, "note": "no decided games in one arm"}
            continue
        p1, p2 = w1 / n1, w2 / n2
        pp = (w1 + w2) / (n1 + n2)
        se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2)) if 0 < pp < 1 else 0.0
        fail = se > 0 and (p2 - p1) < -G4_SE * se
        g4[d] = {"C": f"{w1}/{n1}", "T": f"{w2}/{n2}", "diff_pp": round(100 * (p2 - p1), 1),
                 "se_pp": round(100 * se, 1), "fail": fail}
    rep["G4_per_deck"] = g4
    verdict["G4"] = not any(v["fail"] for v in g4.values())

    # E2: C vs Z event rates, Holm
    rc, rz = rates(arms["C"]["games"]), rates(arms["Z"]["games"])
    common = sorted((set(rc) & set(rz)) - ONLY_017)
    tests = []
    for k in common:
        z, p = clustered_z(rz[k], rc[k])
        tests.append((p, k, z, mean(rz[k]), mean(rc[k])))
    tests.sort()
    m = len(tests)
    holm_fail = []
    for i, (p, k, z, mz, mc) in enumerate(tests):
        if p <= ALPHA / (m - i):
            holm_fail.append(k)
        else:
            break
    rep["E2"] = [{"event": k, "Z_016": round(mz, 3), "C_017": round(mc, 3), "z": round(z, 2), "p": round(p, 4)}
                 for p, k, z, mz, mc in sorted(tests, key=lambda t: t[1])]
    rep["E2_only_in_one_arm"] = {"only_C": sorted(set(rc) - set(rz)), "only_Z": sorted(set(rz) - set(rc))}
    rep["E2_holm_significant"] = holm_fail
    verdict["E2"] = not holm_fail
    rep["games"] = {arm: len(d["games"]) for arm, d in arms.items()}

    # Decision per PREREG
    if not (verdict["E1"] and verdict["E2"]):
        decision = "FAIL (equivalence): 0.17.0 changed behaviour with flags off; do not merge the shim branch; find the cause."
    elif verdict["P1"] is None:
        decision = "UNDECIDED: fewer than 20 shim tutor casts in T; run 64 more cEDH-A games in C and T (new seeds) and read P1 once."
    elif all(verdict[k] for k in ("P1", "P2", "P3", "G1", "G2", "G3", "G4")):
        decision = "PASS: R1 ships the hotfix (tag shim v0.17.0, pin it, MTG_PLAN_VERSION=2 at the R1 deploy)."
    else:
        decision = ("FAIL (hotfix): R1 ships the truth patch with MTG_PLAN_VERSION=1; run one arm per flag "
                    "(MTG_PLAN_FIX) overnight and re-decide.")
    rep["verdict"] = verdict
    rep["decision"] = decision

    print(json.dumps(rep, indent=1, default=str))
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
