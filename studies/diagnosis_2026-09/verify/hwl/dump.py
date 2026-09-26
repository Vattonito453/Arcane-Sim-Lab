import json, glob, os
S = r"C:/Users/Vatto/Magic Rules Engine/studies"
for f in sorted(glob.glob(S + "/behavior_rubric/runs_agent_shipping/plans/*.json")):
    d = json.load(open(f, encoding="utf-8"))
    print("=====", os.path.basename(f))
    for name, p in d["decks"].items():
        print("--", name, "keys:", sorted(p.keys()))
        print("   commanders:", p.get("commanders"), "n_lines:", len(p.get("lines", [])), "tutors:", len(p.get("tutors", [])))
        for ln in p.get("lines", []):
            print("   L", ln["cards"], "|", "; ".join(ln.get("produces", []))[:160])
