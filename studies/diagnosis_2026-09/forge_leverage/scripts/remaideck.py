import zipfile, re, json, glob, os, collections
Z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
hints = {}
for n in Z.namelist():
    if not n.endswith(".txt"): continue
    t = Z.read(n).decode("utf-8", "replace")
    m = re.search(r"^Name:(.+)$", t, re.M)
    if not m: continue
    name = m.group(1).strip()
    rem = "All" if re.search(r"^AI:RemoveDeck:All", t, re.M) else ("Random" if re.search(r"^AI:RemoveDeck:Random", t, re.M) else None)
    ailogic = sorted(set(re.findall(r"AILogic\$ ?([A-Za-z0-9_]+)", t)))
    hints[name] = {"rem": rem, "ailogic": ailogic}
    # alternate faces
    for alt in re.findall(r"^ALTERNATE\s*$.*?^Name:(.+)$", t, re.M | re.S):
        hints.setdefault(alt.strip(), hints[name])
json.dump(hints, open(os.path.join(os.path.dirname(__file__), "card_hints.json"), "w"))
print("cards", len(hints), "RemAll", sum(1 for v in hints.values() if v["rem"] == "All"), "RemRandom", sum(1 for v in hints.values() if v["rem"] == "Random"))

def deck_cards(path):
    cards = []
    sec = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("["): sec = line.strip("[]").lower(); continue
        if sec in ("main", "commander") and line:
            m = re.match(r"(\d+)\s+(.+?)(\|.*)?$", line)
            if m: cards.append((int(m.group(1)), m.group(2).strip(), sec))
    return cards

R = "C:/Users/Vatto/Magic Rules Engine/"
decks = sorted(glob.glob(R + "studies/human_ceiling/decks/*/dck/*.dck"))
tot = collections.Counter(); per = []
for d in decks:
    cs = deck_cards(d)
    n = sum(q for q, _, _ in cs)
    ra = [c for q, c, s in cs if hints.get(c, {}).get("rem") == "All"]
    rr = [c for q, c, s in cs if hints.get(c, {}).get("rem") == "Random"]
    miss = [c for q, c, s in cs if c not in hints]
    per.append((os.path.relpath(d, R), n, len(ra), len(rr), len(miss)))
    tot["cards"] += n; tot["all"] += len(ra); tot["rand"] += len(rr); tot["miss"] += len(miss)
    tot.update({"c:" + c: 1 for c in ra})
print("cEDH decks", len(decks), "cards", tot["cards"], "RemoveDeck:All", tot["all"], "Random", tot["rand"], "unmatched", tot["miss"])
for p in per: print("  ", p)
top = sorted(((v, k[2:]) for k, v in tot.items() if k.startswith("c:")), reverse=True)[:45]
print("most common RemoveDeck:All cards in cEDH decks:", top)

# plan lines and tutors
pl = collections.Counter()
seen_piece = set(); seen_tutor = set()
for f in glob.glob(R + "studies/behavior_rubric/plans_*.json"):
    D = json.load(open(f))["decks"]
    for deck, p in D.items():
        for line in p.get("lines", []):
            for c in line["cards"]:
                seen_piece.add((deck, c))
        for t in p.get("tutors", []):
            seen_tutor.add((deck, t))
def frac(s):
    a = sum(1 for _, c in s if hints.get(c, {}).get("rem") == "All")
    r = sum(1 for _, c in s if hints.get(c, {}).get("rem") == "Random")
    return len(s), a, r
print("plan line pieces (deck,card) n/All/Random:", frac(seen_piece))
print("plan tutors (deck,card) n/All/Random:", frac(seen_tutor))
print("flagged tutors:", sorted({c for _, c in seen_tutor if hints.get(c, {}).get("rem")}))
print("flagged pieces:", sorted({c for _, c in seen_piece if hints.get(c, {}).get("rem") == "All"}))
