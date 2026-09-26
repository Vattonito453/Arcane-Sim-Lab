import json, collections, re
from pathlib import Path

HERE = Path(__file__).parent
reps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE / "reports").glob("*.json"))]

def narrow_win(prod):  # the other investigator's stated rule
    return any(re.search(r"win the game|damage|life ?loss|lose the game|lose life", p, re.I) for p in prod)

def broad_win(prod):  # adds outputs that end the game through combat on their own
    return narrow_win(prod) or any(re.search(
        r"combat phases|infinitely (powerful|large)|tokens with haste|poison|exile your library", p, re.I) for p in prod)

rows = collections.OrderedDict()
for r in reps:
    gm = {g["n"]: g for g in r["games"]}
    for deck, d in r["decks"].items():
        for c in d["combos"]:
            k = (r["_set"], r["_pod"], deck, c["id"])
            row = rows.setdefault(k, {"cards": c["cards"], "produces": c["produces"], "games": []})
            for g in c["games"]:
                x = gm[g["n"]]
                row["games"].append(dict(g, method=x["method"], detail=x.get("detail", ""), ended=x["ended_turn"]))

fired = {k: v for k, v in rows.items() if any(g["won"] and g["assembled_turn"] is not None for g in v["games"])}
print("rows", len(rows), "fired", len(fired))

for label, fn in [("narrow", narrow_win), ("broad", broad_win)]:
    nonwin = {k: v for k, v in fired.items() if not fn(v["produces"])}
    win = {k: v for k, v in fired.items() if fn(v["produces"])}
    conv = [g for v in nonwin.values() for g in v["games"] if g["won"] and g["assembled_turn"] is not None]
    meth = collections.Counter(g["method"] for g in conv)
    delay = [g["ended"] - g["assembled_turn"] for g in conv]
    b = collections.Counter("same" if d == 0 else "1-3" if d < 4 else ">=4" for d in delay)
    print(f"\n[{label}] fired rows: nonwin={len(nonwin)} win={len(win)} ({len(nonwin)/len(fired):.0%} nonwin)")
    print("  nonwin converted game-rows:", len(conv), dict(meth), dict(b))
    print("  win rows:")
    for k, v in win.items():
        cg = [g for g in v["games"] if g["won"] and g["assembled_turn"] is not None]
        print("   ", k[0], k[2], " + ".join(v["cards"]), "|", v["produces"][:3], "| conv", len(cg),
              [(g["method"], g.get("detail", "")[:40], g["ended"] - g["assembled_turn"]) for g in cg])

# Features of 'nonwin' (narrow) rows that are combat-kill style
print("\nnarrow-nonwin but broad-win rows:")
for k, v in fired.items():
    if not narrow_win(v["produces"]) and broad_win(v["produces"]):
        cg = [g for g in v["games"] if g["won"] and g["assembled_turn"] is not None]
        print("   ", k[0], k[2], " + ".join(v["cards"]), "|", [p for p in v["produces"] if re.search('combat|infinitely|haste|poison|exile', p, re.I)],
              "| conv", len(cg), [(g["ended"] - g["assembled_turn"]) for g in cg])

# Distinct combo rows fired, whole-sample: how many converted game-rows total and methods
allconv = [g for v in fired.values() for g in v["games"] if g["won"] and g["assembled_turn"] is not None]
print("\nall fired converted game-rows", len(allconv), collections.Counter(g["method"] for g in allconv))
