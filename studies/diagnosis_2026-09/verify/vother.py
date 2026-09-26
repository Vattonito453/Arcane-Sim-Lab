import glob, os, re, json, collections, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vfunnel as V
S = V.STUDIES
sets = {
 "br_agent_shipping": (glob.glob(S + "/behavior_rubric/runs_agent_shipping/*.jsonl"), lambda fp, pod: S + f"/behavior_rubric/runs_agent_shipping/plans/plans_{pod}.json"),
 "tt_stage2": (glob.glob(S + "/tutor_targeting/runs_stage2/*.jsonl"), lambda fp, pod: S + "/tutor_targeting/runs_stage2/plans_20260825_175454_pid81260.json"),
 "hc_stock": (glob.glob(S + "/human_ceiling/runs/*.jsonl"), lambda fp, pod: S + f"/behavior_rubric/runs_agent_shipping/plans/plans_{pod}.json"),
}
allf = [f for v in sets.values() for f in v[0]]
V.scan_types(allf)
PODS = ["2iA_Jt0d6sM", "5A6o18Bra0Y", "B421mac67IE", "Bq-nFi0f1jA", "CxKMqO36DdM", "OuY6mdiXbHU", "n7WpsqsZtdQ", "sZA0KqXCGrY"]
for arm, (files, pr) in sets.items():
    rows = []
    shims = collections.Counter()
    for fp in sorted(files):
        pod = next((p for p in PODS if p in os.path.basename(fp)), None)
        lp = pr(fp, pod)
        if not os.path.exists(lp):
            print("  skip", fp); continue
        try:
            meta, _ = V.games_of(fp)
        except Exception as e:
            print("  bad", fp, e); continue
        if meta is None:
            print("  nometa", fp); continue
        shims[(meta.get("shim"), tuple(sorted(set(meta["agents"]))))] += 1
        rows += V.analyze(fp, V.load_lines(lp))
    for grp in sorted({r["agent"] for r in rows}):
        R = [r for r in rows if r["agent"] == grp]
        a = [r for r in R if r["assembled"] is not None]
        c = [r for r in a if r["converted"]]
        print(arm, grp, "n", len(R), "asm", len(a), "conv", len(c), "wins", sum(r["won"] for r in R), "spell", sum(1 for r in c if r["spell_win"]))
    print("   shims", dict(shims))
