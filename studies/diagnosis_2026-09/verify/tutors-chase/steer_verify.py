import json, glob, re, collections, hashlib, os
from pathlib import Path
R = "C:/Users/Vatto/Magic Rules Engine/studies"
LU = json.load(open("lines_union.json"))
WIN = {"Win the game", "Win the game at the beginning of your next upkeep", "Infinite damage",
       "Near-infinite damage", "Infinite lifeloss", "Infinite mill", "Near-infinite mill",
       "Infinite combat phases", "Infinite creature tokens with haste",
       "Infinitely powerful creatures you control until end of turn",
       "Infinitely large creature until end of turn", "Infinite power for any creature", "Lock",
       "Opponents put all cards in hand on the bottom of their library on each of their draw steps"}
def cls(prod):
    return "win" if any(p in WIN for p in prod) else "resource"
deckcls = {}
for d, ls in LU.items():
    deckcls[d] = [(set(c), cls(p), p) for c, p in ls]
def classify(deck, card):
    ls = deckcls.get(deck) or []
    if any(card in c for c, k, _ in ls if k == "win"): return "win"
    if any(card in c for c, k, _ in ls if k == "resource"): return "resource"
    return "none"
res = collections.Counter(); bydir = collections.Counter(); bycard = collections.Counter()
seen_hash = {}; dup = 0; files = 0
for f in glob.glob(R + "/**/*.jsonl", recursive=True):
    h = hashlib.md5(open(f, "rb").read()).hexdigest()
    if h in seen_hash: dup += 1; continue
    seen_hash[h] = f
    with open(f, encoding="utf-8", errors="replace") as fh:
        try: meta = json.loads(fh.readline())
        except Exception: continue
        if meta.get("rec") != "meta" or not meta.get("decks"): continue
        seat = {}
        for p, d in zip(meta["players"], meta["decks"]):
            if "human_ceiling" in d:
                seat[p] = Path(d.replace("\\", "/")).stem
        if not seat: continue
        files += 1
        sd = str(Path(f).relative_to(R).parent).replace("\\", "/")
        for line in fh:
            if '"tutor_steer"' not in line and '"tutor_cast"' not in line: continue
            r = json.loads(line); deck = seat.get(r.get("player"))
            if not deck: continue
            det = r.get("detail", "")
            if r["event"] == "tutor_steer":
                m = re.search(r"mode=(\w+).*steer=(.+?) over=", det)
                if m: mode, card = m.group(1), m.group(2)
                else:
                    m = re.match(r"^(.+?) over (.+)$", det)
                    if not m: continue
                    mode, card = "legacy", m.group(1)
            else:
                m = re.match(r"^(.+) seeking (.+)$", det)
                if not m: continue
                mode, card = "tutor_cast", m.group(2)
            k = classify(deck, card)
            res[(mode, k)] += 1
            bydir[(sd, mode, k)] += 1
            bycard[(mode, k, deck, card)] += 1
print("files", files, "dups skipped", dup)
for mode in ("combo", "plan", "legacy", "tutor_cast"):
    tot = sum(v for (m, k), v in res.items() if m == mode)
    if not tot: continue
    print(mode, tot, {k: (v, round(100*v/tot)) for (m, k), v in res.items() if m == mode})
json.dump({"|".join(k): v for k, v in bycard.items()}, open("bycard.json", "w"), indent=0)
print("--- top resource-class targets")
agg = collections.Counter()
for (mode, k, deck, card), v in bycard.items():
    if k == "resource": agg[(deck, card)] += v
for x, v in agg.most_common(25): print(v, x)
print("--- by deck share resource (steer+cast)")
dk = collections.defaultdict(collections.Counter)
for (mode, k, deck, card), v in bycard.items(): dk[deck][k] += v
for d, c in sorted(dk.items(), key=lambda kv: -sum(kv[1].values())): print(d, dict(c))
