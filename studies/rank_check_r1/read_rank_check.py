#!/usr/bin/env python3
"""Read the Precon-8 rank check for R1 (see PREREG.md) and, when decided,
append its record to engine/models/rank_checks.json.

    py studies/rank_check_r1/read_rank_check.py                    # report only
    py studies/rank_check_r1/read_rank_check.py --write-record     # report + record
    py studies/rank_check_r1/read_rank_check.py --runs <dir>       # any cohort-layout arm

The metric is the one a run's prediction page implies: the Spearman rank
correlation, across the cohort's decks, between the prediction the shipped
model serves for each deck (engine/predict.py Predictor.predict, fed that
deck's survival over EVERY game it played under this pilot, censored games
included, exactly as mtg_engine._read_result_prediction computes it, plus its
committed training features creatures and avg_cmc) and the deck's human win
rate from playgroup.gg (studies/precon_predict/cohort.json, the 2026-08-03
capture the model was fitted against). PASS iff rho >= 0.40, read to three
decimals, on a decided run (at least 64 decks with 16 games, at least 95% of
the 768 games, one pilot). Everything else printed is reported, not gated.

Reading an older arm (for example the stock arm in the main checkout's
studies/precon_predict/runs_stock) is allowed and is how this reader was
validated; only a decided reading of the R1 pilot can write a record.
"""
from __future__ import annotations

import argparse, json, random, re, statistics as st, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_rank_check as R  # noqa: E402  (design constants, cells, the prereg guard)

REPO = R.REPO
sys.path.insert(0, str(REPO / "engine"))
sys.path.insert(0, str(REPO / "studies/precon_predict"))
import model as M  # noqa: E402  (the cohort's own spearman: average ranks for ties)
import pilot as P  # noqa: E402
import predict  # noqa: E402

THRESHOLD = 0.40
MIN_GAMES_PER_DECK = 16
MIN_DECKS = 64
MIN_GAME_SHARE = 0.95
EXPECTED_PILOT = "plan/0.17.0/v2"
METRIC = "spearman(predicted, human)"
SEAT = re.compile(r"^Ai\((\d+)\)-")
RECORDS = REPO / "engine/models/rank_checks.json"


def _base(path: str) -> str:
    return str(path).replace("\\", "/").rsplit("/", 1)[-1].lower()


def collect(runs: Path) -> dict:
    """Per-deck tallies over every result record, mapped to decks by SEAT."""
    co = R.cohort()
    decks = {c["name"]: {"g": 0, "alive": 0, "timed_out": 0, "turn_capped": 0,
                         "decided": 0, "wins": 0} for c in co}
    pilots, commits, plan_shas, jar_shas = set(), set(), set(), set()
    missing, short, ms = [], [], []
    games = 0
    for cell in R.cells():
        f = runs / f"{cell['name']}.jsonl"
        if not f.exists():
            missing.append(cell["name"])
            continue
        names = [co[i]["name"] for i in cell["order"]]
        meta, results = None, []
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"rec":"meta"' not in line and '"rec":"result"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("rec") == "meta":
                meta = r
            elif r.get("rec") == "result":
                results.append(r)
        if meta and meta.get("decks"):
            got = [_base(d) for d in meta["decks"]]
            want = [_base(d) for d in cell["decks"]]
            if got != want:
                sys.exit(f"{f.name}: seat order {got} is not the design's {want}; "
                         f"refusing to map winners to decks")
        if meta:
            pilots.add(P.run_pilot({
                "agent": f"{P.SHIM_AGENT}/{meta.get('shim', '?')}",
                "agents": meta.get("agents"), "humanized": meta.get("humanized"),
                "planVersions": meta.get("planVersions"),
                "fixFlags": meta.get("fixFlags")})["id"])
            commits.add(meta.get("shimCommit"))
            plan_shas.add(meta.get("plansSha256"))
        prov = f.with_suffix(".cell.json")
        if prov.exists():
            try:
                jar_shas.add(json.loads(prov.read_text(encoding="utf-8")).get("jar_sha256"))
            except ValueError:
                pass
        if len(results) < R.GAMES_PER_CELL:
            short.append(cell["name"])
        for r in results[:R.GAMES_PER_CELL]:
            games += 1
            ms.append(r.get("ms") or 0)
            seats = r.get("seats") or []
            w = None
            if r.get("winner") and not r.get("draw"):
                m = SEAT.match(r["winner"])
                w = int(m.group(1)) - 1 if m else None
            decided = not r.get("timedOut") and w is not None
            for i, nm in enumerate(names):
                d = decks[nm]
                d["g"] += 1
                d["alive"] += 1 if (i < len(seats) and seats[i].get("alive")) else 0
                d["timed_out"] += 1 if r.get("timedOut") else 0
                d["turn_capped"] += 1 if r.get("turnCapped") else 0
                if decided:
                    d["decided"] += 1
                    d["wins"] += 1 if w == i else 0
    return {"decks": decks, "games": games, "missing": missing, "short": short,
            "pilots": sorted(p for p in pilots if p), "shim_commits": sorted(c for c in commits if c),
            "plans_sha256": sorted(s for s in plan_shas if s),
            "jar_sha256": sorted(s for s in jar_shas if s), "ms": ms}


def served(model, survival: float, creatures: float, avg_cmc: float) -> float:
    """The number the page shows: expected_win_rate, clamped and rounded."""
    return model.predict({"survival": survival, "creatures": creatures,
                          "avg_cmc": avg_cmc})["expected_win_rate"]


def second_capture() -> dict:
    out = {}
    p = REPO / "studies/precon_predict/gt_2026-08-26.txt"
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) >= 2:
            try:
                out[parts[0].strip()] = float(parts[1])
            except ValueError:
                pass
    return out


def analyse(c: dict) -> dict:
    model = predict.Predictor.load()
    feats = {r["name"]: r for r in json.loads(
        (REPO / "studies/precon_predict/features.json").read_text(encoding="utf-8"))}
    co = {x["name"]: x for x in R.cohort()}
    rows = []
    for nm, d in c["decks"].items():
        if d["g"] < MIN_GAMES_PER_DECK:
            continue
        f = feats[nm]
        surv = 100.0 * d["alive"] / d["g"]
        rows.append({"deck": nm, "games": d["g"], "survival": round(surv, 2),
                     "predicted": served(model, surv, f["creatures"], f["avg_cmc"]),
                     "human": co[nm]["human"], "creatures": f["creatures"],
                     "avg_cmc": f["avg_cmc"], "decided": d["decided"], "wins": d["wins"],
                     "timed_out": d["timed_out"]})
    n = len(rows)
    design = R.ROUNDS * 16 * 4 * R.GAMES_PER_CELL
    pred = [r["predicted"] for r in rows]
    human = [r["human"] for r in rows]
    surv = [r["survival"] for r in rows]
    rho = M.spearman(pred, human) if n >= 3 else float("nan")
    decided = (n >= MIN_DECKS and c["games"] >= MIN_GAME_SHARE * design
               and len(c["pilots"]) == 1)
    out = {"n_decks": n, "games": c["games"], "design_games": design,
           "missing_cells": len(c["missing"]), "short_cells": len(c["short"]),
           "pilots": c["pilots"], "shim_commits": c["shim_commits"],
           "plans_sha256": c["plans_sha256"], "jar_sha256": c["jar_sha256"],
           "metric": METRIC, "rho": rho, "threshold": THRESHOLD, "decided": decided,
           "pass": bool(decided and round(rho, 3) >= THRESHOLD)}
    if n < 3:
        return out

    # ---- reported, not gated ------------------------------------------
    mu_surv = model.m["mu"][model.features.index("survival")]
    floor = [served(model, mu_surv, r["creatures"], r["avg_cmc"]) for r in rows]
    rng = random.Random(20261016)
    null = []
    for _ in range(4000):
        s = surv[:]
        rng.shuffle(s)
        null.append(M.spearman([served(model, x, r["creatures"], r["avg_cmc"])
                                for x, r in zip(s, rows)], human))
    null.sort()
    rep = []
    for _ in range(2000):
        p2 = []
        for r in rows:
            p = r["survival"] / 100.0
            k = sum(1 for _ in range(r["games"]) if rng.random() < p)
            p2.append(served(model, 100.0 * k / r["games"], r["creatures"], r["avg_cmc"]))
        rep.append(M.spearman(p2, human))
    rep.sort()
    gt2 = second_capture()
    both = [(r["predicted"], gt2[r["deck"]]) for r in rows if r["deck"] in gt2]
    live_rows, differ = [], 0
    for r in rows:
        try:
            lf = predict.deck_features(co[r["deck"]]["file"])
        except Exception:  # noqa: BLE001
            continue
        if lf["creatures"] != r["creatures"] or abs(lf["avg_cmc"] - r["avg_cmc"]) > 1e-6:
            differ += 1
        live_rows.append((served(model, r["survival"], lf["creatures"], lf["avg_cmc"]),
                          r["human"]))
    dec_rows = [r for r in rows if r["decided"] >= 12]
    all_g = sum(r["games"] for r in rows)
    ms = [x for x in c["ms"] if x]
    out["reported"] = {
        "pearson": M.pearson(pred, human),
        "mae_pp": sum(abs(a - b) for a, b in zip(pred, human)) / n,
        "bias_pp": sum(a - b for a, b in zip(pred, human)) / n,
        "documented": {"loo_spearman": model.m["loo"]["spearman"],
                       "loo_mae_pp": model.m["loo"]["mae"], "guess_the_mean_mae_pp": 4.249,
                       "stock_arm_in_sample_spearman": 0.544,
                       "agent_0150_arm_in_sample_spearman": 0.508},
        "rho_survival_alone": M.spearman(surv, human),
        "rho_decklist_floor": M.spearman(floor, human),
        "permutation": {"null_mean": st.mean(null), "null_p95": null[int(0.95 * len(null))],
                        "p_null_ge_observed": sum(1 for x in null if x >= rho) / len(null)},
        "sim_noise": {"replicate_mean": st.mean(rep), "replicate_sd": st.pstdev(rep),
                      "replicate_p2_5": rep[int(0.025 * len(rep))]},
        "rho_capture_2026_08_26": M.spearman([a for a, _ in both], [b for _, b in both])
        if len(both) >= 3 else None,
        "live_features": {"rho": M.spearman([a for a, _ in live_rows], [b for _, b in live_rows])
                          if len(live_rows) >= 3 else None,
                          "decks_differing_from_training": differ,
                          "card_cache": str(getattr(predict.cards, "CACHE_PATH", ""))},
        "rho_decided_win_rate": M.spearman([100.0 * r["wins"] / r["decided"] for r in dec_rows],
                                           [r["human"] for r in dec_rows])
        if len(dec_rows) >= 3 else None,
        "survival_mean": st.mean(surv), "survival_sd": st.pstdev(surv),
        "timed_out_share": sum(r["timed_out"] for r in rows) / all_g if all_g else None,
        "game_seconds_mean": st.mean(ms) / 1000 if ms else None,
        "game_seconds_median": st.median(ms) / 1000 if ms else None,
    }
    out["rows"] = sorted(rows, key=lambda r: -r["predicted"])
    return out


def report(a: dict, runs: Path):
    print(f"Precon-8 rank check, read {time.strftime('%Y-%m-%d')}: {runs}")
    print(f"  pilot(s) {a['pilots']}  shim commit {a['shim_commits']}  "
          f"plans {[s[:12] for s in a['plans_sha256']]}")
    print(f"  games {a['games']}/{a['design_games']}, decks with >= {MIN_GAMES_PER_DECK} "
          f"games {a['n_decks']}, missing cells {a['missing_cells']}, short cells {a['short_cells']}")
    if a["n_decks"] < 3:
        print("  too little data to compute anything")
        return
    verdict = ("PASS" if a["pass"] else "FAIL") if a["decided"] else "NOT DECIDED"
    print(f"\n  PRIMARY  {METRIC} = {a['rho']:.3f}  threshold {THRESHOLD:.2f}  ->  {verdict}")
    x = a["reported"]
    print("\n  reported, not gated")
    print(f"    pearson {x['pearson']:+.3f}   MAE {x['mae_pp']:.2f} pp   bias {x['bias_pp']:+.2f} pp "
          f"(documented LOO MAE {x['documented']['loo_mae_pp']:.2f}, guess-the-mean 4.25)")
    print(f"    documented LOO rho {x['documented']['loo_spearman']:.3f}; in-sample on the stock "
          f"arm 0.544, on the 0.15.0 arm 0.508")
    print(f"    rho, survival alone {x['rho_survival_alone']:+.3f}; decklist floor "
          f"{x['rho_decklist_floor']:+.3f}")
    pm = x["permutation"]
    print(f"    permutation null (survival shuffled): mean {pm['null_mean']:.3f}, p95 "
          f"{pm['null_p95']:.3f}, P(null >= observed) {pm['p_null_ge_observed']:.4f}")
    sn = x["sim_noise"]
    print(f"    sim-noise replicates: mean {sn['replicate_mean']:.3f} sd {sn['replicate_sd']:.3f} "
          f"2.5% {sn['replicate_p2_5']:.3f}")
    if x["rho_capture_2026_08_26"] is not None:
        print(f"    rho against the 2026-08-26 capture {x['rho_capture_2026_08_26']:+.3f}")
    lf = x["live_features"]
    if lf["rho"] is not None:
        print(f"    rho with live deck features {lf['rho']:+.3f} ({lf['decks_differing_from_training']} "
              f"decks differ from training; cache {lf['card_cache']})")
    if x["rho_decided_win_rate"] is not None:
        print(f"    rho, decided-game win rate vs human {x['rho_decided_win_rate']:+.3f}")
    print(f"    survival mean {x['survival_mean']:.1f} sd {x['survival_sd']:.1f} (fit: 30.2 / 11.5); "
          f"timed out {100 * (x['timed_out_share'] or 0):.1f}%; game "
          f"{x['game_seconds_mean'] or 0:.0f} s mean, {x['game_seconds_median'] or 0:.0f} s median")


def write_record(a: dict, release: str, prereg: str) -> dict:
    if not a["decided"]:
        sys.exit("not decided: no record written (the label keeps saying no check has run)")
    if a["pilots"] != [EXPECTED_PILOT]:
        sys.exit(f"pilot {a['pilots']} is not the R1 pilot {EXPECTED_PILOT}: no record written")
    if a["jar_sha256"] and a["jar_sha256"] != [R.JAR_SHA256]:
        sys.exit(f"cells ran on jar(s) {a['jar_sha256']}, not {R.JAR_SHA256}: no record written")
    data = json.loads(RECORDS.read_text(encoding="utf-8"))
    checks = data["checks"] if isinstance(data, dict) else data
    if any(c.get("release") == release and c.get("pilot") == EXPECTED_PILOT for c in checks):
        sys.exit(f"a {release} record for {EXPECTED_PILOT} already exists; records are never "
                 f"edited, and a re-run cannot overturn a reading (PREREG.md)")
    rec = {"release": release, "date": time.strftime("%Y-%m-%d"), "pilot": EXPECTED_PILOT,
           "jar_sha": R.JAR_SHA256, "plan_version": 2, "metric": METRIC,
           "value": round(a["rho"], 3), "threshold": THRESHOLD, "pass": a["pass"],
           "n_decks": a["n_decks"], "games": a["games"], "study": "studies/rank_check_r1",
           "prereg_commit": prereg.split()[0] if prereg else None}
    checks.append(rec)
    RECORDS.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default=None, help="cell folder (default: $RANK_CHECK_OUT/runs)")
    ap.add_argument("--release", default="R1")
    ap.add_argument("--write-record", action="store_true",
                    help="append the decided reading to engine/models/rank_checks.json")
    a = ap.parse_args()
    runs = Path(a.runs).resolve() if a.runs else R.OUT / "runs"
    prereg = R.assert_preregistered() if a.write_record else ""
    res = analyse(collect(runs))
    report(res, runs)
    R.OUT.mkdir(parents=True, exist_ok=True)
    dest = R.OUT / f"reading_{runs.name}.json"
    dest.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\n  reading -> {dest}")
    if a.write_record:
        rec = write_record(res, a.release, prereg)
        print(f"  record  -> {RECORDS}: {json.dumps(rec)}")
        print("  commit engine/models/rank_checks.json with studies/rank_check_r1/RESULTS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
