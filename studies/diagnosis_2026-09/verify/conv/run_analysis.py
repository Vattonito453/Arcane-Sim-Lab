"""Independent re-run of engine/analysis.analyse over the 4 study run sets.
Writes per-file analysis reports to ./reports/*.json (scratch only).
MTG_DATA_DIR must point at a scratch copy of the caches; MTG_OFFLINE=1.
"""
import json, os, sys, re
from pathlib import Path

REPO = Path(r"C:/Users/Vatto/Magic Rules Engine")
sys.path.insert(0, str(REPO / "engine"))
import analysis, shim_log_adapter  # noqa

HERE = Path(__file__).parent
OUT = HERE / "reports"
OUT.mkdir(exist_ok=True)
ST = REPO / "studies"
DECKS = ST / "human_ceiling" / "decks"

jobs = []  # (set, pod, label, result-dict)
for setname, sub, pat in [("016_engine", "agent_viability/runs_016_engine", "cell_*.jsonl"),
                          ("015_default", "agent_viability/runs_015_default", "cell_*.jsonl"),
                          ("shipping", "behavior_rubric/runs_agent_shipping", "*.jsonl")]:
    for f in sorted((ST / sub).glob(pat)):
        if f.name == "results.jsonl":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        meta = json.loads(text.splitlines()[0])
        res = shim_log_adapter.parse_shim_jsonl(text, source=str(f))
        res.setdefault("meta", {})
        res["meta"]["decks"] = [Path(p.replace("\\", "/")).name for p in meta.get("decks", [])]
        pod = Path(meta["decks"][0].replace("\\", "/")).parent.parent.name
        res["file"] = f"{setname}/{f.name}"
        jobs.append((setname, pod, f.name, res))

for f in sorted((ST / "human_ceiling/runs").glob("sim_*.json")):
    res = json.loads(f.read_text(encoding="utf-8"))
    m = re.search(r"_hc(?:pilot)?(.+)_rotated", f.name)
    tag = m.group(1)
    pod = next(p.name for p in DECKS.iterdir() if p.name.replace("-", "").replace("_", "") == tag.replace("-", "").replace("_", "") or p.name.replace("_", "") == tag)
    res["file"] = f"hc/{f.name}"
    jobs.append(("hc_stock", pod, f.name, res))

tot = 0
for setname, pod, name, res in jobs:
    rep = analysis.analyse(res, deck_dirs=[DECKS / pod / "dck"], fetch=False)
    rep["_set"] = setname
    rep["_pod"] = pod
    tot += rep["summary"]["games"]
    (OUT / f"{setname}__{name}.report.json").write_text(json.dumps(rep), encoding="utf-8")
    unk = [n for n, d in rep["decks"].items() if d["combo_status"] != "ok"]
    print(setname, pod, name, rep["summary"]["games"], "decks", len(rep["decks"]), "unknown", unk)
print("TOTAL GAMES", tot)
