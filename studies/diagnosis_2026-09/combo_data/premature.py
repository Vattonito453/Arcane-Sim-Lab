import json, glob, re, collections
from pathlib import Path
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
audit = {r["deck"]: r for r in json.load(open("plan_audit.json")) if "/" in r["deck"]}
hand_pieces = {}  # deck -> set of H-zone pieces
for tag, r in audit.items():
    s = set()
    for a in r["lines"]:
        for c, z in a["nonB"].items():
            if z == "H": s.add(c)
    hand_pieces[tag] = s
tot = collections.Counter(); card_ct = collections.Counter(); all_cc = 0
for f in glob.glob(R + "/**/*.jsonl", recursive=True):
    with open(f, encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
        try: meta = json.loads(first)
        except: continue
        if meta.get("rec") != "meta" or not meta.get("decks"): continue
        seat = {}
        for p, d in zip(meta["players"], meta["decks"]):
            parts = Path(d.replace("\\", "/")).parts
            if "human_ceiling" in d: seat[p] = parts[-3] + "/" + Path(d).stem
        for line in fh:
            if '"combo_cast"' not in line: continue
            r = json.loads(line)
            m = re.match(r"^(.+) \((\d+)/(\d+) online\)$", r["detail"])
            if not m: continue
            all_cc += 1
            card, k, n = m.group(1), int(m.group(2)), int(m.group(3))
            tag = seat.get(r["player"])
            if not tag: tot["non-cEDH combo_cast"] += 1; continue
            completes = k + 1 == n
            tot["completing" if completes else "developing"] += 1
            if card in hand_pieces.get(tag, ()) and not completes:
                tot["PREMATURE hand-zone piece"] += 1; card_ct[card] += 1
print("combo_cast events parsed:", all_cc, dict(tot))
print("premature casts of pieces Spellbook says must be cast last from hand:", card_ct.most_common())
