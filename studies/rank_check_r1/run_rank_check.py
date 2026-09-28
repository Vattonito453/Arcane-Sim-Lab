#!/usr/bin/env python3
"""Precon-8 rank check for R1 (see PREREG.md): the 66-precon cohort under the
R1 pilot, so read_rank_check.py can ask whether the shipped playgroup model
still ranks decks when fed this pilot's simulation.

    py studies/rank_check_r1/run_rank_check.py plans            # version-2 plans, no games
    py studies/rank_check_r1/run_rank_check.py smoke            # 1 game, never read
    py studies/rank_check_r1/run_rank_check.py run --workers 8  # 384 cells, 768 games

Reuses the cohort tooling: studies/precon_predict/cohort.json for the decks
and human win rates, and run_cohort.pods_for_round for the pods (seeded by
round, so these are the same pods the stock arm the model was fitted on and
the 0.15.0 arm played). Cells are named as run_cohort names them, so
decided.py, richsignal.py and divergence.py read this output unchanged.

Refuses to play a game unless PREREG.md, this file and read_rank_check.py
are committed and unchanged, the shim jar matches the tested hash, and
MTG_PLAN_FIX and MTG_PLAN_FEEDBACK_APPLY are unset (the R1 pilot is version
2 with every flag, and no feedback nudge). Resumable: a cell with its games
already recorded is skipped, so rerunning `run` retries only what failed.
Raw output, plans and caches go under $RANK_CHECK_OUT (default: a scratch
folder), never into git.
"""
from __future__ import annotations

import argparse, hashlib, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
COHORT_DIR = REPO / "studies/precon_predict"
sys.path.insert(0, str(COHORT_DIR))
from run_cohort import pods_for_round  # noqa: E402  (the existing pod draw)

SCRATCH = Path(r"C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad")
OUT = Path(os.environ.get("RANK_CHECK_OUT", SCRATCH / "rank_check_r1"))
FORGE = Path(r"C:/Users/Vatto/forge/forge-gui-desktop-2.0.13-jar-with-dependencies.jar")
JAR = Path(os.environ.get("RANK_CHECK_JAR", SCRATCH / "g0a/shim-0.17.0-b8894e1.jar"))
JAR_SHA256 = "c2273bef30d7cd9edb20d711f81bce01444470a91e9d15bbf23f2e3fd3081dfd"

# The design, fixed by PREREG.md. Changing any of these is a new study.
ROUNDS = 6               # rounds 0..5 of pods_for_round: 16 pods each
GAMES_PER_CELL = 2       # per seat rotation; 4 rotations per pod per round
CLOCK = 900              # production per-game clock (CLAUDE.md, run_sim)
MAX_TURNS = 120          # production turn cap
HEAP = "3g"              # as G0a and the cohort arms; heap does not steer decisions
SEED_BASE = 2026101600   # --seed-forge = SEED_BASE + round*1000 + pod*10 + rotation
CELL_WALL = GAMES_PER_CELL * (CLOCK + 150) + 300   # hang detector per JVM, not a budget
PREREG_FILES = ("PREREG.md", "run_rank_check.py", "read_rank_check.py")


def cohort() -> list[dict]:
    return json.loads((COHORT_DIR / "cohort.json").read_text(encoding="utf-8"))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True).stdout.strip()


def assert_preregistered() -> str:
    """The commit that fixed this study's protocol AND code, or exit.

    Every file must be tracked and unchanged, and the commit returned is the
    latest one that touched ANY of them, not only PREREG.md: every cell
    records it, and the reader refuses to write a record unless every cell
    ran under the commit that is current at read time. So an edit to the
    reader or runner committed after the first game (an edited reader could
    drift toward the data) cannot hide behind the PREREG's older commit."""
    rels = [f"studies/rank_check_r1/{f}" for f in PREREG_FILES]
    for rel in rels:
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", rel],
                                 capture_output=True, text=True).returncode == 0
        dirty = git("status", "--porcelain", "--", rel)
        if not tracked or dirty:
            sys.exit(f"refusing to run: {rel} is not committed and unchanged "
                     f"({dirty or 'untracked'})")
    return git("log", "-1", "--format=%H %cI", "--", *rels)


def assert_pilot_env():
    """The plans are built explicitly as version 2 with every flag; an
    environment that asks for anything else is a different arm."""
    for var, ok in (("MTG_PLAN_FIX", {"", "all"}), ("MTG_PLAN_VERSION", {"", "2"})):
        val = (os.environ.get(var) or "").strip().lower()
        if val not in ok:
            sys.exit(f"refusing to run: {var}={val!r}; the R1 pilot is version-2 plans "
                     f"with every fix flag")
    if os.environ.get("MTG_PLAN_FEEDBACK_APPLY", "0") == "1":
        sys.exit("refusing to run: MTG_PLAN_FEEDBACK_APPLY=1; production runs with it off")


def assert_jar():
    if not JAR.is_file():
        sys.exit(f"shim jar missing: {JAR}")
    got = sha256(JAR)
    if got != JAR_SHA256:
        sys.exit(f"shim jar hash mismatch: {got} != {JAR_SHA256} (the R1 pilot is "
                 f"0.17.0 at b8894e1, the jar G0a tested)")
    if not FORGE.is_file():
        sys.exit(f"Forge jar missing: {FORGE}")


def plans_path() -> Path:
    return OUT / "plans_v2.json"


def build_plans():
    """Version-2 plans for all 66 precons, one file, as production builds
    them (deck_plan.build_plans, plan_version=2, every fix flag), from a
    scratch copy of the committed caches plus Forge's own card index.

    Refuses once any cell has run: a rebuild fetches card facts again, and a
    run whose cells played two different plans files is not one pilot."""
    assert_pilot_env()
    started = sorted((OUT / "runs").glob("*.cell.json")) if (OUT / "runs").is_dir() else []
    if plans_path().is_file() and started:
        sys.exit(f"refusing to rebuild {plans_path()}: {len(started)} cell(s) of the run "
                 f"already played with it. Resume with `run`; a new plans file is a new run "
                 f"in a new RANK_CHECK_OUT.")
    cache = OUT / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    for f in ("card_cache.json", "combo_cache.json"):
        if not (cache / f).exists() and (REPO / "engine" / f).exists():
            shutil.copy(REPO / "engine" / f, cache / f)
    os.environ["MTG_DATA_DIR"] = str(cache)
    if not (cache / "forge_index").exists():
        subprocess.run([sys.executable, str(REPO / "engine/forge_index.py"), "build"],
                       check=True, env=dict(os.environ, MTG_DATA_DIR=str(cache)))
    sys.path.insert(0, str(REPO / "engine"))
    import deck_plan  # noqa: E402  (after MTG_DATA_DIR, which cards.py reads at import)
    files = [c["file"] for c in cohort()]
    missing = [f for f in files if not Path(f).is_file()]
    if missing:
        sys.exit(f"{len(missing)} cohort deck files missing, e.g. {missing[:2]}")
    plans = deck_plan.build_plans(files, fetch=True, plan_version=2, fix="all")
    decks = plans["decks"]
    if len(decks) != len(files):
        sys.exit(f"built {len(decks)} plans for {len(files)} decks: names collide")
    bad = [f"{n} cov={p.get('factsCoverage', 0):.2f}" for n, p in decks.items()
           if p.get("factsCoverage", 0) < 0.9]
    if bad:
        sys.exit(f"degraded plan data (warm the cache first): {bad}")
    wrong = [n for n, p in decks.items()
             if p.get("planVersion") != 2 or not all((p.get("fix") or {}).values())
             or set(p.get("fix") or {}) != set(deck_plan.V2_FIX)]
    if wrong:
        sys.exit(f"not version 2 with every flag: {wrong}")
    OUT.mkdir(parents=True, exist_ok=True)
    plans_path().write_text(json.dumps(plans, indent=2), encoding="utf-8")
    lines = sum(len(p.get("lines", [])) for p in decks.values())
    print(f"{plans_path()}  {len(decks)} decks, version 2, every fix flag; "
          f"{lines} win-band lines in total; sha256 {sha256(plans_path())}")


def cells(rounds: int = ROUNDS) -> list[dict]:
    """Round-major, so a run in progress is complete round by round."""
    co = cohort()
    out = []
    for rnd in range(rounds):
        for pod_i, pod in enumerate(pods_for_round(co, rnd)):
            for inv in range(4):
                order = pod[inv:] + pod[:inv]
                out.append({"rnd": rnd, "pod": pod_i, "inv": inv, "order": order,
                            "decks": [co[i]["file"] for i in order],
                            "seed": SEED_BASE + rnd * 1000 + pod_i * 10 + inv,
                            "name": f"c_r{rnd}_p{pod_i:02d}_i{inv}"})
    return out


def results_in(p: Path) -> int:
    if not p.exists():
        return 0
    return p.read_text(encoding="utf-8", errors="replace").count('"rec":"result"')


def play(cell: dict, runs: Path, games: int, prereg: str, plans_sha: str,
         repo_commit: str) -> str:
    out = runs / f"{cell['name']}.jsonl"
    if results_in(out) >= games:
        return f"{cell['name']} cached"
    prov = out.with_suffix(".cell.json")
    attempts = 1
    if prov.exists():
        try:
            attempts = int(json.loads(prov.read_text(encoding="utf-8")).get("attempts", 0)) + 1
        except (ValueError, OSError):
            attempts = 1
    cmd = ["java", f"-Xmx{HEAP}", "-cp", f"{JAR}{os.pathsep}{FORGE}", "simlab.shim.SimShim",
           "--decks", *cell["decks"], "--games", str(games),
           "--timeout", str(CLOCK), "--max-turns", str(MAX_TURNS),
           "--plans", str(plans_path()),
           "--seat-pilots", ",".join(["plan:SimLabHuman"] * 4),
           "--seed-forge", str(cell["seed"]), "--out", str(out)]
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    t0 = time.time()
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        try:
            rc = subprocess.run(cmd, cwd=str(FORGE.parent), stdout=subprocess.DEVNULL,
                                stderr=eh, timeout=CELL_WALL).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    prov.write_text(json.dumps({
        "cell": cell["name"], "round": cell["rnd"], "pod": cell["pod"], "rotation": cell["inv"],
        "seed": cell["seed"], "started": started, "wall_s": round(time.time() - t0, 1),
        "rc": rc, "results": results_in(out), "games": games, "attempts": attempts,
        "jar": str(JAR), "jar_sha256": JAR_SHA256, "plans_sha256": plans_sha,
        # The checkout the run was launched from, read once before any game;
        # read here, at the end of a cell, it named whatever was committed
        # while the JVM played (the smoke recorded a later commit).
        "repo_commit": repo_commit, "prereg_commit": prereg, "cmd": cmd},
        indent=1), encoding="utf-8")
    return f"{cell['name']} rc={rc} results={results_in(out)}/{games} ({time.time() - t0:.0f}s)"


def _start():
    prereg = assert_preregistered()
    assert_pilot_env()
    assert_jar()
    if not plans_path().is_file():
        sys.exit(f"no plans at {plans_path()}; run `plans` first")
    return prereg, sha256(plans_path()), git("rev-parse", "HEAD")


def smoke():
    """One game in the first cell's seat order, into OUT/smoke. The reader
    never reads this folder; it proves the invocation, the plans and the
    pilot identity before an overnight run is committed to."""
    prereg, plans_sha, repo = _start()
    runs = OUT / "smoke"
    runs.mkdir(parents=True, exist_ok=True)
    print(play(cells(1)[0], runs, 1, prereg, plans_sha, repo), flush=True)


def run(workers: int):
    prereg, plans_sha, repo = _start()
    runs = OUT / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    todo = cells()
    done = sum(1 for c in todo if results_in(runs / f"{c['name']}.jsonl") >= GAMES_PER_CELL)
    print(f"rank check R1: {len(todo)} cells ({len(todo) * GAMES_PER_CELL} games), "
          f"{done} already complete, {workers} JVMs; prereg {prereg}; out {runs}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for msg in ex.map(lambda c: play(c, runs, GAMES_PER_CELL, prereg, plans_sha, repo),
                          todo):
            print(msg, flush=True)
    left = [c["name"] for c in todo if results_in(runs / f"{c['name']}.jsonl") < GAMES_PER_CELL]
    print(f"incomplete cells: {len(left)}" + (f" (rerun `run` to retry): {left[:8]}" if left else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("plans", "smoke", "run"))
    ap.add_argument("--workers", type=int, default=8, help="parallel JVMs for `run` (default 8)")
    a = ap.parse_args()
    if a.cmd == "plans":
        build_plans()
    elif a.cmd == "smoke":
        smoke()
    else:
        run(a.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
