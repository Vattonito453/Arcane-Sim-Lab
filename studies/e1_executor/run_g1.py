#!/usr/bin/env python3
"""G1 runner (see PREREG.md): the E1 executor prototype against stock, on
fresh gate seeds.

    py studies/e1_executor/run_g1.py check     # provenance only: files, hashes, plans; no game
    py studies/e1_executor/run_g1.py outcome   # S1 S2 S3 S4 S6 x stock, exec x 20 trials
    py studies/e1_executor/run_g1.py c1        # the 20 C1 boards x stock, exec, plan017 x 1
    py studies/e1_executor/run_g1.py timing    # S1 S2 S3 S4 S6 x exec x 8, 2-core affinity
    py studies/e1_executor/run_g1.py all       # check, outcome, c1, timing, in that order

Refuses to run unless PREREG.md, this file, read_g1.py, the five step files,
the scenario runner and writer and the scenario files are committed and
unchanged, and every hash pinned below (and in PREREG.md) matches. Every phase
is one studies/scenarios/run_scenarios.py invocation with a fixed command
line. Raw output goes under $G1_OUT (default a scratch folder), never into git.
Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRATCH = Path(r"C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/"
               r"7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad")
OUT = Path(os.environ.get("G1_OUT", SCRATCH / "g1" / "runs"))
DATA_DIR = SCRATCH / "g0a" / "cache_cedh"
SUITE = REPO / "studies" / "scenarios" / "suite"
STEPS = HERE / "steps"
RUNNER = REPO / "studies" / "scenarios" / "run_scenarios.py"

JAR = SCRATCH / "e1" / "shim-0.18.0-proto-88e7564.jar"
JAR_SHA = "3795f534d24093f98e629f63553d19bab3d24b555295a24f688f3c84d69a0a0a"
JAR_COMMIT = "88e756456304"
REF_JAR = SCRATCH / "harness" / "shim-0.17.1-967cb71.jar"       # plan017, C1 reference only
REF_JAR_SHA = "56758de2551b70e8510545f5b426fcdc5fc2adfcb6781f570e9d89375ff064fe"

# Shim repository: the Java diff and the lint (read_g1.py).
SHIM_REPO = Path(r"C:/Users/Vatto/simlab-forge-shim")
SHIM_WT = SCRATCH / "e1" / "shim_wt"                            # exec-proto checked out at the tip
SHIM_BASE = "13eeed73d15131293138a6842b5cad3cb7591527"          # shim-0.17.1-scenario
SHIM_TIP = "88e756456304a616640b23b5d246975bfe4a76fb"           # exec-proto
CARDSFOLDER = Path(r"C:/Users/Vatto/forge/res/cardsfolder")

SCENARIOS = ["s1_kiki_conscripts", "s2_derevi_emiel_cradle", "s3_druid_reconfiguration",
             "s4_magda_clock_torque", "s6_scepter_reversal"]
LABEL = dict(zip(SCENARIOS, ["S1", "S2", "S3", "S4", "S6"]))
STEP_SHA = {
    "s1_kiki_conscripts": "bed09a9eae7e19cee9a4ca646e3720a9b0ee43996d055c7fe3bb6a68b39f7599",
    "s2_derevi_emiel_cradle": "4967a9f5803b1a376d9dad03f92d0cda87248a2df57caef9532bc23db18d3ff6",
    "s3_druid_reconfiguration": "ac7c18f431f3ad453fd013b32bfc604dac087c706c1eaf9dcf5f560123414ad6",
    "s4_magda_clock_torque": "d72f8f7e908eba7354014798ec4091387546aad4502da27e1751b7c034f6b019",
    "s6_scepter_reversal": "3642c962b996357cb5bebd1054bc408ddf43b438561e6d94b3acedb136ecb1e0",
}
# Exec-arm plans files (the step file merged into the line deck's plan); C1 has none.
PLANS_SHA = {
    "s1_kiki_conscripts": "674c60fbf617913bedd7a8236abb5efea3af3b8c4d62bf225e6008e233d1cbdf",
    "s2_derevi_emiel_cradle": "66a52be86ab8a571f5267384442b967844f5ea99e45b6c5dc8ee616ebd8bf937",
    "s3_druid_reconfiguration": "17d1662ab732926bb91b46911b6b5b64b67bb47c9264fb5c82e6f3800b120c31",
    "s4_magda_clock_torque": "5ccd66fcf2e58c05c714520b26bd10f9ec145758afa44440738f35a3610a54b9",
    "s6_scepter_reversal": "6b84338908025e8efd5aadd6d39c7103f2c5ceaeb40c002c15ebaa660f391651",
    "c1": "ed88b2e47b64ba49af70c738c8da9e36db08f73ff816c3025e0a76739e51d7d6",
}
FILE_SHA = {
    "studies/scenarios/run_scenarios.py": "d9f093ff62f93ee5ca94dd3c9bc3470502f47e87b790a529659ba06b4d58235c",
    "studies/scenarios/writer.py": "a9262ff17af826ac2a64ddc91c15c2ff4908ad592c2872d90a0693b5f59174fc",
    "studies/scenarios/suite/s1_kiki_conscripts.json": "9e81670ec8a3060592100ac428c883121865b78038e73f041456abacd9da6450",
    "studies/scenarios/suite/s2_derevi_emiel_cradle.json": "ba6fd057b6d402023c03038b8e37fce66013dcbefb1137da99db01f8a1c38366",
    "studies/scenarios/suite/s3_druid_reconfiguration.json": "36b415f2fd64b5e188f856716548349d49fe851fbbc9288bfba9502bda426ba4",
    "studies/scenarios/suite/s4_magda_clock_torque.json": "36ff3b2f0509422e0d21b693169aef7d2b9287504319431cdb481e427639d5d2",
    "studies/scenarios/suite/s6_scepter_reversal.json": "61749cc34aacba09e06f12942d31707d3ef04628261cea7661080a805213e642",
}
# The 20 C1 boards and their source record, as one digest (c1_digest()).
C1_DIGEST = "d1741f78381335a0ae489c310a13862bff620a7c157c87a9be2ee066d1e60c3c"

DEV_RANGE = (2026200000, 2026200999)
GATE_MIN = 2026102300
PARALLEL = 8
AFFINITY = "3,C,30,C0,300,C00,3000,C000"       # CPUs 0-15 as eight disjoint pairs
ACTIVE_CPUS = "-XX:ActiveProcessorCount=2"
PHASES = {
    "outcome": {"arms": "stock,exec", "trials": 20, "seed": 2026102300},
    "c1": {"arms": "stock,exec,plan017", "trials": 1, "seed": 2026102320},
    "timing": {"arms": "exec", "trials": 8, "seed": 2026102340},
}
REF_ARMS = {"plan017": {"pilot": "plan:SimLabHuman", "plan_version": 2, "fix": "all", "jar": str(REF_JAR)}}
PREREG_FILES = ["studies/e1_executor/PREREG.md", "studies/e1_executor/run_g1.py",
                "studies/e1_executor/read_g1.py"]


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def c1_files() -> list[Path]:
    return sorted((SUITE / "c1").glob("c1_*.json"))


def c1_digest() -> str:
    h = hashlib.sha256()
    for p in c1_files() + [SUITE / "c1" / "sources.json"]:
        h.update(f"{p.name} {sha256(p)}\n".encode())
    return h.hexdigest()


def scenario_files(phase: str) -> list[Path]:
    return c1_files() if phase == "c1" else [SUITE / f"{s}.json" for s in SCENARIOS]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


def assert_preregistered() -> str:
    """Every gate input committed and unchanged; returns the PREREG commit."""
    rels = PREREG_FILES + [f"studies/e1_executor/steps/{s}.json" for s in SCENARIOS] + list(FILE_SHA) \
        + [str(p.relative_to(REPO)).replace("\\", "/") for p in c1_files()] \
        + ["studies/scenarios/suite/c1/sources.json"]
    bad = []
    for rel in rels:
        st = git("status", "--porcelain", "--", rel).stdout.strip()
        tracked = git("ls-files", "--error-unmatch", rel).returncode == 0
        if st or not tracked:
            bad.append(f"{rel} ({st or 'untracked'})")
    if bad:
        sys.exit("refusing to run: not committed and unchanged: " + "; ".join(bad))
    for sid, want in STEP_SHA.items():
        got = sha256(STEPS / f"{sid}.json")
        if got != want:
            sys.exit(f"refusing to run: step file {sid} is {got}, PREREG pins {want}")
    for rel, want in FILE_SHA.items():
        got = sha256(REPO / rel)
        if got != want:
            sys.exit(f"refusing to run: {rel} is {got}, pinned {want}")
    if c1_digest() != C1_DIGEST:
        sys.exit(f"refusing to run: the C1 boards digest is {c1_digest()}, pinned {C1_DIGEST}")
    for jar, want in ((JAR, JAR_SHA), (REF_JAR, REF_JAR_SHA)):
        got = sha256(jar)
        if got != want:
            sys.exit(f"refusing to run: {jar.name} is {got}, PREREG pins {want}")
    for name, ph in PHASES.items():
        lo, hi = ph["seed"], ph["seed"] + ph["trials"] - 1
        assert lo >= GATE_MIN and not (DEV_RANGE[0] <= hi and lo <= DEV_RANGE[1]), (name, lo, hi)
    return git("log", "-1", "--format=%H %cI", "--", "studies/e1_executor/PREREG.md").stdout.strip()


def check_plans() -> None:
    """Build the plans exactly as run_scenarios will and compare them with the
    pinned hashes (no game is played)."""
    sys.path.insert(0, str(RUNNER.parent))
    import run_scenarios as rs
    import writer
    out = OUT / "check_plans"
    out.mkdir(parents=True, exist_ok=True)
    arm = rs.ARMS["exec"]
    for sp in [SUITE / f"{s}.json" for s in SCENARIOS] + [c1_files()[0]]:
        sc = writer.load(sp)
        sid = sc.get("id") or sp.stem
        decks = [writer.resolve_path(s["deck"], sp.parent).resolve() for s in sc["seats"]]
        plans = rs.build_plans(decks, arm, out, str(DATA_DIR), False)
        found = rs.load_steps(STEPS, sid)
        if found:
            plans = rs.merge_steps(plans, found[1], out, sid)
        key = "c1" if sid.startswith("c1_") else sid
        got = sha256(plans)
        if got != PLANS_SHA[key]:
            sys.exit(f"refusing to run: {sid} plans {got}, PREREG pins {PLANS_SHA[key]}")
        print(f"plans ok: {sid} {got[:12]}")


def load_monitor(path: Path, stop: threading.Event) -> None:
    """Once a minute: Java processes on the box and CPU load (other agents
    share it and are not controlled)."""
    with path.open("a", encoding="utf-8") as fh:
        while not stop.is_set():
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq java.exe", "/FO", "CSV", "/NH"],
                               capture_output=True, text=True)
            java = sum(1 for l in r.stdout.splitlines() if l.startswith('"java.exe"'))
            c = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage "
                                "-Average).Average"], capture_output=True, text=True)
            try:
                load = float(c.stdout.strip())
            except ValueError:
                load = None
            fh.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "java": java, "cpu": load}) + "\n")
            fh.flush()
            stop.wait(60)


def phase_cmd(name: str) -> list[str]:
    ph = PHASES[name]
    cmd = [sys.executable, "-u", str(RUNNER), *map(str, scenario_files(name)),
           "--jar", str(JAR), "--out", str(OUT / name), "--arms", ph["arms"],
           "--trials", str(ph["trials"]), "--parallel", str(PARALLEL), "--seed", str(ph["seed"]),
           "--data-dir", str(DATA_DIR), "--steps", str(STEPS)]
    if name == "c1":
        arms_file = OUT / "c1_arms.json"
        arms_file.write_text(json.dumps(REF_ARMS, indent=1), encoding="utf-8")
        cmd += ["--arms-file", str(arms_file)]
    if name == "timing":
        cmd += ["--affinity", AFFINITY, f"--jvm-arg={ACTIVE_CPUS}"]
    return cmd


def run_phase(name: str, prereg: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = phase_cmd(name)
    rec = {"phase": name, "prereg_commit": prereg, "repo_head": git("rev-parse", "HEAD").stdout.strip(),
           "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "cmd": cmd, "jar_sha256": JAR_SHA}
    hist = OUT / f"{name}.phase.jsonl"
    stop = threading.Event()
    mon = threading.Thread(target=load_monitor, args=(OUT / f"{name}.load.jsonl", stop), daemon=True)
    mon.start()
    print(f"G1 {name}: prereg {prereg}", flush=True)
    t0 = time.time()
    with (OUT / f"{name}.log").open("a", encoding="utf-8") as log:
        rc = subprocess.run(cmd, cwd=str(REPO), stdout=log, stderr=subprocess.STDOUT).returncode
    stop.set()
    rec.update({"finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "rc": rc, "wall_s": round(time.time() - t0, 1)})
    with hist.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"G1 {name}: rc {rc}, {rec['wall_s']} s", flush=True)
    return rc


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what not in ("check", "all", *PHASES):
        sys.exit(__doc__)
    prereg = assert_preregistered()
    check_plans()
    print(f"provenance ok; PREREG commit {prereg}", flush=True)
    if what == "check":
        return
    for name in (list(PHASES) if what == "all" else [what]):
        if run_phase(name, prereg) != 0:
            sys.exit(f"phase {name} failed")


if __name__ == "__main__":
    main()
