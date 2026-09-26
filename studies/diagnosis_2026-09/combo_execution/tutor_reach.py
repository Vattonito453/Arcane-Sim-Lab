"""Can the tutor the shim chose (tutor_cast "X seeking Y") legally find Y at all?
Reads each tutor's Forge script: the ChangeType$ of its library search, and
compares against the sought card's type line. Heuristic, printed with examples."""
import json, glob, re, collections, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from forge_cards import load
idx = load()
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
PATS = ["agent_viability/runs_015_default/cell_*.jsonl", "agent_viability/runs_winmax/cell_*.jsonl",
        "agent_viability/runs_016_engine/cell_*.jsonl", "behavior_rubric/runs_agent_shipping/*.jsonl",
        "tutor_targeting/runs_stage2/*.jsonl"]


def types_of(name):
    e = idx.get(name)
    if not e:
        return set()
    m = re.search(r"^Types:(.*)$", e["face"], re.M)
    return set(m.group(1).split()) if m else set()


def search_types(tutor):
    e = idx.get(tutor)
    if not e:
        return None
    t = e["text"]
    # library searches: ChangeZone/ChangeZoneAll with Origin$ Library, or Dig-based
    outs = []
    for m in re.finditer(r"Origin\$ ?Library[^\n]*", t):
        line = m.group(0)
        ct = re.search(r"ChangeType\$ ?([^|\n]+)", line)
        if ct:
            outs.append(ct.group(1).strip())
    # also lines where ChangeType precedes Origin
    for m in re.finditer(r"ChangeType\$ ?([^|\n]+)[^\n]*Origin\$ ?Library", t):
        outs.append(m.group(1).strip())
    return outs or None


def can_find(tutor, target):
    sts = search_types(tutor)
    if sts is None:
        return None  # unknown mechanism (Dig, Wish, Pact of X...), not judged
    tt = types_of(target)
    perm = bool(tt & {"Creature", "Artifact", "Enchantment", "Land", "Planeswalker", "Battle"})
    for st in sts:
        for tok in st.split(","):
            base = tok.split(".")[0].strip()
            if base in ("Card", "Any"):
                return True
            if base == "Permanent" and perm:
                return True
            if base in tt:
                return True
            if base == "Equipment" and "Equipment" in tt:
                return True
    return False


out = collections.Counter()
ex = collections.defaultdict(list)
for pat in PATS:
    for f in glob.glob(S + pat):
        for l in open(f, encoding="utf-8"):
            if '"tutor_cast"' not in l:
                continue
            r = json.loads(l)
            tutor, want = r["detail"].split(" seeking ", 1)
            k = can_find(tutor, want)
            key = {True: "tutor CAN find the sought piece", False: "tutor CANNOT find it (type mismatch)",
                   None: "not judged (non-ChangeZone search)"}[k]
            out[key] += 1
            if len(ex[key]) < 8:
                ex[key].append(f"{tutor} -> {want}")
tot = sum(out.values())
print("tutor_cast events:", tot)
for k, v in out.most_common():
    print(f"  {v:4d} ({100*v/tot:.0f}%) {k}")
for k, v in ex.items():
    print(k, "e.g.:", "; ".join(v))
