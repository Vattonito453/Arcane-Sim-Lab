import json, glob, re, collections, os, sys
from pathlib import Path
os.environ["MTG_DATA_DIR"] = str(Path("data").resolve()); os.environ["MTG_OFFLINE"] = "1"
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import cards
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
pairs = collections.Counter()
for f in glob.glob(R + "/**/*.jsonl", recursive=True):
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"tutor_cast"' not in line: continue
            r = json.loads(line)
            m = re.match(r"^(.+) seeking (.+)$", r["detail"])
            if m: pairs[(m.group(1), m.group(2))] += 1
names = sorted({x for p in pairs for x in p})
facts = cards.get_many(names, fetch=False)
def F(n): return facts.get(cards.key(n)) or facts.get(n) or {}
clause_re = re.compile(r"search your librar(?:y|ies) for ([^.;\n]*)", re.I)
def fits(tutor, target):
    t = F(tutor); x = F(target)
    if not t or not x: return None
    m = clause_re.search(t.get("oracle_text") or "")
    if not m: return None
    cl = m.group(1).lower(); tl = (x.get("type_line") or "").lower(); mv = x.get("cmc") or 0
    if re.search(r"\ba card\b|\bcards\b", cl) and not re.search(r"creature|artifact|enchantment|instant|sorcery|equipment|aura|legendary|goblin|dwarf|land", cl):
        return True
    ok = False
    for kind in ("creature", "artifact", "enchantment", "instant", "sorcery", "planeswalker", "equipment", "legendary"):
        if kind in cl and kind in tl: ok = True
    if "goblin" in cl: ok = ok or "goblin" in tl
    if not ok: return False
    mm = re.search(r"mana value (\d+) or less", cl)
    if mm and mv > int(mm.group(1)): return False
    mm = re.search(r"toughness (\d+) or less", cl)
    if mm:
        try:
            if int(x.get("toughness") or 99) > int(mm.group(1)): return False
        except ValueError: pass
    return True
res = collections.Counter(); bad = collections.Counter()
for (t, x), n in pairs.items():
    v = fits(t, x)
    res[v] += n
    if v is False: bad[(t, x)] += n
print("tutor_cast events:", sum(pairs.values()), "fit check:", dict(res))
print("examples of tutors cast for a target they cannot legally find:")
for k, v in bad.most_common(20): print("  ", v, k)
