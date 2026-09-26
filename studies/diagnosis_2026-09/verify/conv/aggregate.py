import json, collections
from pathlib import Path

HERE = Path(__file__).parent
reps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE / "reports").glob("*.json"))]

# ---- per-file rows (what one results page renders) ----
file_rows = []
for r in reps:
    gmeth = {g["n"]: g for g in r["games"]}
    for deck, d in r["decks"].items():
        for c in d["combos"]:
            file_rows.append((r, deck, c, gmeth))
print("per-file rows:", len(file_rows), "fired:", sum(1 for _, _, c, _ in file_rows if c["reading"] == "fired"))

# ---- aggregated rows at various keys ----
def agg(keyf):
    rows = collections.OrderedDict()
    for r, deck, c, gmeth in file_rows:
        k = keyf(r, deck, c)
        row = rows.setdefault(k, {"cards": c["cards"], "produces": c["produces"], "games": []})
        for g in c["games"]:
            gm = gmeth[g["n"]]
            row["games"].append(dict(g, method=gm["method"], detail=gm.get("detail"), ended=gm["ended_turn"], file=r["file"]))
    return rows

for label, kf in [("set,pod,deck,combo", lambda r, d, c: (r["_set"], r["_pod"], d, c["id"])),
                  ("pod,deck,combo", lambda r, d, c: (r["_pod"], d, c["id"])),
                  ("deck,combo", lambda r, d, c: (d, c["id"])),
                  ("set,deck,combo", lambda r, d, c: (r["_set"], d, c["id"]))]:
    rows = agg(kf)
    fired = [k for k, v in rows.items() if any(g["won"] and g["assembled_turn"] is not None for g in v["games"])]
    print(f"{label}: rows={len(rows)} fired={len(fired)}")

# produces features across all fired per-file rows
feat = collections.Counter()
for r, deck, c, _ in file_rows:
    if c["reading"] == "fired":
        for p in c["produces"]:
            feat[p] += 1
print("\nFEATURES on fired per-file rows:")
for k, v in feat.most_common():
    print(f"  {v:4d} {k}")
json.dump({"n": len(file_rows)}, open(HERE / "agg_meta.json", "w"))
