"""Tutor census: which tutors are in each cEDH/precon deck, which the plan's
regex sees, and which the shim's tutor_cast path could actually cast.
Read-only over the repo."""
import json, re, glob, sys, collections
from pathlib import Path

ROOT = Path(r"C:/Users/Vatto/Magic Rules Engine")
sys.path.insert(0, str(ROOT / "engine"))
cache = json.loads((ROOT / "engine/card_cache.json").read_text(encoding="utf-8"))

def fact(n):
    k = n.lower()
    return cache.get(k) or cache.get(k.split(" // ")[0]) or {}

# deck_plan.py's regexes, verbatim
TUTOR_CLAUSE = re.compile(r"search your librar(?:y|ies) for ([^.;\n]*)", re.I)
LAND_CLAUSE = re.compile(r"land|plains|island|swamp|mountain|forest|gate\b", re.I)
FINISHER = re.compile(r"wins? the game|loses? the game|combat damage to a player|"
                      r"infect|damage can't be prevented", re.I)

# broader: any search of own library (incl. "and/or graveyard"), transmute,
# plus known non-"search" tutors
BROAD = re.compile(r"search(?:es)? your library(?: and/or graveyard)? for ([^.;\n]*)", re.I)
KNOWN_EXTRA = {"Demonic Consultation": "dig-named", "Tainted Pact": "dig",
               "Scheming Symmetry": "tutor-both", "Wishclaw Talisman": "tutor"}

def read_dck(p):
    cmd, main = [], []
    sec = None
    for line in Path(p).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith("["):
            sec = line.strip("[]").lower(); continue
        m = re.match(r"(\d+)\s+(.+?)(?:\|.*)?$", line)
        if not m: continue
        (cmd if sec == "commander" else main if sec == "main" else []).append(m.group(2).strip())
    return cmd, main

def classify(n):
    f = fact(n)
    text = f.get("oracle_text") or ""
    tline = f.get("type_line") or ""
    if not f:
        return None
    is_land = "Land" in tline and "Creature" not in tline
    plan_tutor = False
    if not is_land:
        tm = TUTOR_CLAUSE.search(text)
        plan_tutor = bool(tm and not LAND_CLAUSE.search(tm.group(1)))
    bm = BROAD.search(text)
    broad = False
    how = []
    if bm and not LAND_CLAUSE.search(bm.group(1)):
        broad = True
    if re.search(r"\btransmute\b", text, re.I):
        broad = True; how.append("transmute")
    if n in KNOWN_EXTRA:
        how.append(KNOWN_EXTRA[n])
    if not broad and not how:
        return None
    # how is the search reached?
    low = text.lower()
    idx = low.find("search your library")
    pre = low[:idx] if idx >= 0 else ""
    if "transmute" in how:
        mode = "transmute(activated from hand)"
    elif is_land:
        mode = "land ability"
    elif re.search(r"\binstant\b|\bsorcery\b", tline, re.I) and not re.search(r"\{t\}|:\s", pre[-60:]):
        mode = "spell"
    elif re.search(r"when .* enters|when .* dies|whenever", pre[-120:]):
        mode = "trigger"
    elif ":" in pre[-80:]:
        mode = "activated"
    else:
        mode = "spell" if "Instant" in tline or "Sorcery" in tline else "permanent-other"
    return {"plan_tutor": plan_tutor, "broad": broad, "mode": mode, "extra": how,
            "type": tline, "finisher_regex": bool(FINISHER.search(text)),
            "is_land": is_land}

def main():
    rows = []
    decks = sorted(glob.glob(str(ROOT / "studies/human_ceiling/decks/*/dck/*.dck")))
    per_deck = {}
    miss_counter = collections.Counter()
    mode_counter = collections.Counter()
    tot_broad = tot_plan = 0
    for d in decks:
        cmd, main = read_dck(d)
        names = cmd + main
        res = {}
        for n in names:
            c = classify(n)
            if c: res[n] = c
        pod = Path(d).parts[-3]
        key = f"{pod}/{Path(d).stem}"
        per_deck[key] = res
        for n, c in res.items():
            if c["broad"] or c["extra"]:
                if "dig" in "".join(c["extra"]) and not c["broad"]:
                    continue
                tot_broad += 1
                mode_counter[c["mode"]] += 1
                if c["plan_tutor"]:
                    tot_plan += 1
                else:
                    miss_counter[(n, c["mode"], c["type"][:40])] += 1
    print(f"cEDH decks: {len(decks)}; tutor copies (broad def, excl digs): {tot_broad}; seen by plan regex: {tot_plan}")
    print("by mode:", dict(mode_counter))
    print("\nMISSED by plan regex (name, mode, type): decks")
    for k, v in miss_counter.most_common():
        print("  ", v, k)
    # tutors the plan sees but tutor_cast can't use correctly
    bad = collections.Counter()
    for key, res in per_deck.items():
        for n, c in res.items():
            if c["plan_tutor"] and c["mode"] in ("transmute(activated from hand)", "activated", "land ability"):
                bad[(n, c["mode"])] += 1
    print("\nIn plan.tutors but tutor_cast (castableSpell: sa.isSpell only) cannot fire its search:")
    for k, v in bad.most_common():
        print("  ", v, k)
    # finisher-regex false positives among tutors / pacts
    json.dump({k: v for k, v in per_deck.items()}, open(Path(__file__).parent / "census.json", "w"), indent=1)

if __name__ == "__main__":
    main()
