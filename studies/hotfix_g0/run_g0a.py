#!/usr/bin/env python3
"""G0a runner (see PREREG.md): arms C, T and Z on cEDH-A and Richard's pod.

    py studies/hotfix_g0/run_g0a.py plans      # build version-1 and version-2 plans
    py studies/hotfix_g0/run_g0a.py run        # 36 cells, at most 12 JVMs

Refuses to run unless PREREG.md and read_g0a.py are committed and unchanged.
Raw output, plans and decks go under $G0A_OUT (default: a scratch folder),
never into git. Richard's decks and caches are user data and are read from
$G0A_PRIVATE.
"""
from __future__ import annotations

import hashlib, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SCRATCH = Path(r"C:/Users/Vatto/AppData/Local/Temp/claude/C--Users-Vatto-Magic-Rules-Engine/7a2e31e0-09c8-49d0-ab6f-f767ccb4d74a/scratchpad")
OUT = Path(os.environ.get("G0A_OUT", SCRATCH / "g0a"))
PRIVATE = Path(os.environ.get("G0A_PRIVATE", SCRATCH / "richard"))
FORGE = Path(r"C:/Users/Vatto/forge/forge-gui-desktop-2.0.13-jar-with-dependencies.jar")
JARS = {
    "0.17.0": (OUT / "shim-0.17.0-b8894e1.jar", "c2273bef30d7cd9edb20d711f81bce01444470a91e9d15bbf23f2e3fd3081dfd"),
    "0.16.0": (SCRATCH / "r0-shim-0.16.0-62fe295.jar", "f40ae8d2e1b49d921b1ed22a3eb1eb23ec61cdf6d60400d1e2d8d6e792ee8cd9"),
}
ARMS = {  # arm -> (jar, plan version, seeded)
    "C": ("0.17.0", 1, True),
    "T": ("0.17.0", 2, True),
    "Z": ("0.16.0", 1, False),
}
CEDH_PODS = ["n7WpsqsZtdQ", "2iA_Jt0d6sM"]
SEED_BASE = 2026092700


def beds() -> dict[str, dict]:
    b = {}
    for pod in CEDH_PODS:
        decks = sorted((REPO / "studies/human_ceiling/decks" / pod / "dck").glob("*.dck"))
        assert len(decks) == 4, (pod, decks)
        b[pod] = {"decks": decks, "games": 8, "cache": OUT / "cache_cedh"}
    b["richard"] = {"decks": [PRIVATE / "dck/kess_reanimator_305b76d7.dck",
                              PRIVATE / "dck/skrat_s_revenge_239c6293.dck",
                              PRIVATE / "dck/stella_lee_wild_card_79f6872f.dck",
                              REPO / "engine/decks/krenko_goblins.dck"],
                    "games": 4, "cache": OUT / "cache_richard"}
    return b


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def assert_preregistered():
    for f in ("PREREG.md", "read_g0a.py", "run_g0a.py"):
        rel = f"studies/hotfix_g0/{f}"
        st = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", rel],
                            capture_output=True, text=True).stdout.strip()
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", rel],
                                 capture_output=True, text=True).returncode == 0
        if st or not tracked:
            sys.exit(f"refusing to run: {rel} is not committed and unchanged ({st or 'untracked'})")
    commit = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%H %cI", "--",
                             "studies/hotfix_g0/PREREG.md"], capture_output=True, text=True).stdout.strip()
    return commit


def build_plans():
    import importlib
    for name, bed in beds().items():
        cache = bed["cache"]
        cache.mkdir(parents=True, exist_ok=True)
        src = PRIVATE / "cache" if name == "richard" else REPO / "engine"
        for f in ("card_cache.json", "combo_cache.json"):
            if not (cache / f).exists() and (src / f).exists():
                shutil.copy(src / f, cache / f)
        os.environ["MTG_DATA_DIR"] = str(cache)
        if not (cache / "forge_index").exists():
            subprocess.run([sys.executable, str(REPO / "engine/forge_index.py"), "build"], check=True,
                           env=dict(os.environ, MTG_DATA_DIR=str(cache)))
        sys.path.insert(0, str(REPO / "engine"))
        for mod in [m for m in list(sys.modules) if m in ("deck_plan", "cards", "combos", "forge_index", "combo_bands", "plan_feedback")]:
            del sys.modules[mod]
        dp = importlib.import_module("deck_plan")
        for v in (1, 2):
            plans = dp.build_plans([str(d) for d in bed["decks"]], fetch=True, plan_version=v)
            bad = [f"{n} cov={p.get('factsCoverage', 0):.2f}" for n, p in plans["decks"].items()
                   if p.get("factsCoverage", 0) < 0.9]
            if bad:
                sys.exit(f"{name} v{v}: degraded plan data: {bad}")
            out = OUT / f"plans_{name}_v{v}.json"
            out.write_text(json.dumps(plans, indent=2), encoding="utf-8")
            lines = {n: len(p.get("lines", [])) for n, p in plans["decks"].items()}
            print(f"{name} v{v}: {out.name} lines={lines}")


def cell(spec) -> str:
    arm, bed_name, rot, bed, prereg = spec
    jar_key, version, seeded = ARMS[arm]
    jar = JARS[jar_key][0]
    out = OUT / "runs" / arm / f"{bed_name}_rot{rot}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.read_text(encoding="utf-8", errors="replace").count('"rec":"result"') >= bed["games"]:
        return f"{arm} {bed_name} rot{rot} cached"
    decks = bed["decks"][rot:] + bed["decks"][:rot]
    plans = OUT / f"plans_{bed_name}_v{version}.json"
    cmd = ["java", "-Xmx3g", "-cp", f"{jar}{os.pathsep}{FORGE}", "simlab.shim.SimShim",
           "--decks", *[str(d) for d in decks], "--games", str(bed["games"]),
           "--timeout", "900", "--max-turns", "120", "--plans", str(plans),
           "--seat-pilots", ",".join(["plan:SimLabHuman"] * 4), "--out", str(out)]
    if seeded:
        pod_i = (CEDH_PODS + ["richard"]).index(bed_name)
        cmd += ["--seed-forge", str(SEED_BASE + pod_i * 100 + rot)]
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with out.with_suffix(".err").open("w", encoding="utf-8") as eh:
        rc = subprocess.run(cmd, cwd=str(FORGE.parent), stdout=subprocess.DEVNULL, stderr=eh).returncode
    (out.with_suffix(".cell.json")).write_text(json.dumps(
        {"arm": arm, "bed": bed_name, "rot": rot, "started": started, "rc": rc,
         "jar": str(jar), "plans": str(plans), "plans_sha256": sha256(plans),
         "prereg_commit": prereg, "cmd": cmd}, indent=1), encoding="utf-8")
    return f"{arm} {bed_name} rot{rot} rc={rc}"


def run():
    prereg = assert_preregistered()
    for key, (jar, want) in JARS.items():
        got = sha256(jar)
        if got != want:
            sys.exit(f"jar {key} hash mismatch: {got} != {want}")
    specs = [(arm, name, rot, bed, prereg) for arm in ARMS for name, bed in beds().items() for rot in range(4)]
    print(f"G0a: {len(specs)} cells, prereg commit {prereg}", flush=True)
    with ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(cell, specs):
            print(r, flush=True)


if __name__ == "__main__":
    {"plans": build_plans, "run": run}[sys.argv[1]]()
