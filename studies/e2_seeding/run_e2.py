#!/usr/bin/env python3
"""E2 runner (see PREREG.md): does --seed-forge pair opening hands?

    py studies/e2_seeding/run_e2.py run        # 26 runs, at most 4 JVMs
    py studies/e2_seeding/run_e2.py dry-run    # print the commands only

Refuses to run unless PREREG.md, run_e2.py and read_e2.py are committed and
unchanged, and unless the shim jar, the Forge jar, the plans file and the
four decks hash to the pre-registered values. Raw output goes under $E2_OUT
(default: a scratch folder), never into git.

Two phases: every replicate-a run finishes before any replicate-b run
starts, so the two replicates of a seed never run at the same moment.
"""
from __future__ import annotations

import hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRATCH = Path(r"C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad")
OUT = Path(os.environ.get("E2_OUT", SCRATCH / "e2_seeding"))
G0A = Path(os.environ.get("G0A_OUT", SCRATCH / "g0a"))
FORGE = Path(r"C:/Users/Vatto/forge/forge-gui-desktop-2.0.13-jar-with-dependencies.jar")
FORGE_SHA = "94d55a3602ede599d6a0884a3fee6c047c3e9cf44356f79898a942ce8f8386d3"
JAR = G0A / "shim-0.17.0-b8894e1.jar"
JAR_SHA = "c2273bef30d7cd9edb20d711f81bce01444470a91e9d15bbf23f2e3fd3081dfd"
PLANS = G0A / "plans_n7WpsqsZtdQ_v2.json"
PLANS_SHA = "9f0588572283ec83169cf3e827e33b03de89eada1bf449da25691644c69a41d9"
POD = "n7WpsqsZtdQ"
DECK_SHA = {  # G0a rotation 0 seat order (sorted file names)
    "magda.dck": "3d442e0e9bf24f0ae3f3e65c6ea58e00287b5dfac96b9ec209464f56a8d036ff",
    "rog_ishai.dck": "43303cf3dc7d55713bf4577c7380c0cf856742d7b9ab52786425dd5a2018324f",
    "selvala_archetype.dck": "1965495503f93cfdeb921526b053b3e7b74314d3de90798cc56cea8136366d72",
    "tymna_thrasios.dck": "dadf1b17f60b78500948771976de7d63f66936b10a9f4b01b04d28c12b0222f9",
}
SEED_BASE = 2026092700      # G0a's n7WpsqsZtdQ rotation-0 seed
STRIDE = 104729             # SimShim.FORGE_SEED_STRIDE
MAX_TURNS = 16
MAX_JVMS = 4
# arm -> (seat pilots, games per run, seed indices k)
ARMS = {
    "E2": (",".join(["plan:SimLabHuman"] * 4), 2, list(range(10))),
    "S": ("plan:SimLabHuman,stock:Default,stock:Default,stock:Default", 1, [0, 1, 2]),
}
REPS = ("a", "b")


def seed(k: int) -> int:
    return SEED_BASE + STRIDE * k


def decks() -> list[Path]:
    ds = sorted((REPO / "studies/human_ceiling/decks" / POD / "dck").glob("*.dck"))
    assert [d.name for d in ds] == list(DECK_SHA), ds
    return ds


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def assert_preregistered() -> str:
    for f in ("PREREG.md", "run_e2.py", "read_e2.py"):
        rel = f"studies/e2_seeding/{f}"
        st = git("status", "--porcelain", "--", rel).stdout.strip()
        tracked = git("ls-files", "--error-unmatch", rel).returncode == 0
        if st or not tracked:
            sys.exit(f"refusing to run: {rel} is not committed and unchanged ({st or 'untracked'})")
    return git("log", "-1", "--format=%H %cI", "--", "studies/e2_seeding/PREREG.md").stdout.strip()


def assert_inputs():
    for label, path, want in (("shim jar", JAR, JAR_SHA), ("forge jar", FORGE, FORGE_SHA),
                              ("plans", PLANS, PLANS_SHA)):
        got = sha256(path)
        if got != want:
            sys.exit(f"{label} hash mismatch: {path} {got} != {want}")
    for d in decks():
        if sha256(d) != DECK_SHA[d.name]:
            sys.exit(f"deck hash mismatch: {d}")


def out_path(arm: str, k: int, rep: str) -> Path:
    return OUT / "runs" / arm / f"seed{k}_{rep}.jsonl"


def command(arm: str, k: int, rep: str) -> list[str]:
    pilots, games, _ = ARMS[arm]
    return ["java", "-Xmx3g", "-cp", f"{JAR}{os.pathsep}{FORGE}", "simlab.shim.SimShim",
            "--decks", *[str(d) for d in decks()], "--games", str(games),
            "--timeout", "900", "--max-turns", str(MAX_TURNS), "--plans", str(PLANS),
            "--seat-pilots", pilots, "--seed-forge", str(seed(k)),
            "--out", str(out_path(arm, k, rep))]


def results_in(path: Path) -> set[int]:
    games = set()
    if not path.exists():
        return games
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"rec":"result"' in line:
            try:
                games.add(json.loads(line)["game"])
            except (ValueError, KeyError):
                pass
    return games


def launch(arm: str, k: int, rep: str, prereg: str, attempt: int) -> int:
    out = out_path(arm, k, rep)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = command(arm, k, rep)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        rc = subprocess.run(cmd, cwd=str(FORGE.parent), stdout=subprocess.DEVNULL, stderr=eh).returncode
    out.with_suffix(".cell.json").write_text(json.dumps(
        {"arm": arm, "k": k, "seed": seed(k), "rep": rep, "attempt": attempt,
         "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rc": rc,
         "games_with_result": sorted(results_in(out)), "jar": str(JAR), "jar_sha256": JAR_SHA,
         "plans": str(PLANS), "plans_sha256": PLANS_SHA, "prereg_commit": prereg, "cmd": cmd},
        indent=1), encoding="utf-8")
    return rc


def cell(spec) -> str:
    arm, k, rep, prereg = spec
    out = out_path(arm, k, rep)
    games = ARMS[arm][1]
    if len(results_in(out)) >= games:
        return f"{arm} seed{k} {rep} cached"
    rc = launch(arm, k, rep, prereg, 1)
    note = f"rc={rc}"
    if 0 not in results_in(out):
        # Pre-registered: re-run once when game 0's result never appeared.
        # The first attempt's files are kept beside the second.
        for suf in (".jsonl", ".err", ".cell.json"):
            p = out.with_suffix(suf)
            if p.exists():
                p.replace(p.with_name(p.name + ".attempt1"))
        rc = launch(arm, k, rep, prereg, 2)
        note += f", no game-0 result: re-run rc={rc}"
    return f"{arm} seed{k} {rep} {note} games={sorted(results_in(out))}"


def specs(rep: str, prereg: str) -> list[tuple]:
    return [(arm, k, rep, prereg) for arm, (_, _, ks) in ARMS.items() for k in ks]


def run():
    prereg = assert_preregistered()
    assert_inputs()
    print(f"E2: prereg commit {prereg}", flush=True)
    for rep in REPS:
        todo = specs(rep, prereg)
        print(f"phase {rep}: {len(todo)} runs, at most {MAX_JVMS} JVMs", flush=True)
        with ThreadPoolExecutor(max_workers=MAX_JVMS) as ex:
            for r in ex.map(cell, todo):
                print(r, flush=True)


def dry_run():
    assert_inputs()
    for rep in REPS:
        for arm, k, _, _ in specs(rep, "dry"):
            print(" ".join(command(arm, k, rep)))


if __name__ == "__main__":
    {"run": run, "dry-run": dry_run}[sys.argv[1]]()
