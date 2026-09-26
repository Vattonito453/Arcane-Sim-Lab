"""Independent Forge script index (read-only on cardsfolder.zip)."""
import json, os, re, zipfile
ZIP = r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "fidx.json")


def build():
    idx = {}
    with zipfile.ZipFile(ZIP) as z:
        for n in z.namelist():
            if not n.endswith(".txt"):
                continue
            txt = z.read(n).decode("utf-8", "replace")
            faces = re.split(r"^ALTERNATE\s*$", txt, flags=re.M)
            for face in faces:
                m = re.search(r"^Name:(.*)$", face, re.M)
                if not m:
                    continue
                name = m.group(1).strip()
                if name not in idx:
                    idx[name] = {"text": txt, "face": face}
    json.dump(idx, open(CACHE, "w", encoding="utf-8"))
    return idx


def load():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    return build()


COLORS = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def card_facts(idx, name):
    e = idx.get(name) or (idx.get(name.split(" // ")[0]) if " // " in name else None)
    if not e:
        return None
    face = e["face"]
    types = (re.search(r"^Types:(.*)$", face, re.M) or [None, ""])[1].split()
    mc = (re.search(r"^ManaCost:(.*)$", face, re.M) or [None, ""])[1].strip()
    cmc = 0
    colors = set()
    if mc and mc != "no cost":
        for sym in mc.split():
            if sym.isdigit():
                cmc += int(sym)
            elif sym == "X":
                pass
            else:
                cmc += 1
                for ch in sym:
                    if ch in COLORS:
                        colors.add(COLORS[ch])
    pt = (re.search(r"^PT:(.*)$", face, re.M) or [None, ""])[1]
    power = None
    if "/" in pt:
        try:
            power = int(pt.split("/")[0])
        except ValueError:
            power = None
    return {"types": set(types), "cmc": cmc, "colors": colors, "power": power}


def searches(idx, name):
    """All library-search ChangeType strings in the card's script (any face)."""
    e = idx.get(name) or (idx.get(name.split(" // ")[0]) if " // " in name else None)
    if not e:
        return None
    out = []
    for line in e["text"].splitlines():
        if "ChangeZone" not in line:
            continue
        if not re.search(r"Origin\$ ?[^|]*Library", line):
            continue
        m = re.search(r"ChangeType\$ ?([^|]+)", line)
        if m:
            ct = m.group(1).strip()
            if "IsRemembered" in ct:
                continue
            out.append(ct)
    if re.search(r"^K:Transmute", e["text"], re.M):
        out.append("TRANSMUTE")
    return out


PERM = {"Creature", "Artifact", "Enchantment", "Land", "Planeswalker", "Battle"}


def _clause_ok(clause, f, strict):
    # clause like "Creature.Green+cmcLEX" or "Card.Artifact" or "Legendary"
    parts = clause.split(".", 1)
    base = parts[0].strip()
    quals = parts[1].split("+") if len(parts) > 1 else []
    t = f["types"]
    if base in ("Card", "Any"):
        pass
    elif base == "Permanent":
        if not (t & PERM):
            return False
    elif base.startswith("non"):
        if base[3:] in t:
            return False
    elif base not in t:
        return False
    for q in quals:
        q = q.strip()
        if q in ("YouOwn", "YouCtrl", "Other", ""):
            continue
        if q in PERM or q in ("Instant", "Sorcery", "Legendary", "Equipment", "Dragon"):
            if q not in t:
                return False
            continue
        if q.startswith("non") and q[3:] in (PERM | {"Legendary", "Instant", "Sorcery"}):
            if q[3:] in t:
                return False
            continue
        if q in COLORS.values():
            if q not in f["colors"]:
                return False
            continue
        if not strict:
            continue
        m = re.match(r"cmc(LE|GE|EQ|LT|GT)(\d+)$", q)
        if m:
            op, v = m.group(1), int(m.group(2))
            c = f["cmc"]
            ok = {"LE": c <= v, "GE": c >= v, "EQ": c == v, "LT": c < v, "GT": c > v}[op]
            if not ok:
                return False
            continue
        m = re.match(r"power(LE|GE)(\d+)$", q)
        if m and f["power"] is not None:
            op, v = m.group(1), int(m.group(2))
            if not ({"LE": f["power"] <= v, "GE": f["power"] >= v}[op]):
                return False
            continue
    return True


def reach(idx, tutor, target, strict=False, tutor_cmc=None):
    """True/False/None(unknown). strict also applies fixed cmc/power quals."""
    s = searches(idx, tutor)
    if not s:
        return None
    f = card_facts(idx, target)
    if f is None:
        return None
    for ct in s:
        if ct == "TRANSMUTE":
            tf = card_facts(idx, tutor)
            if not strict or (tf and tf["cmc"] == f["cmc"]):
                return True
            continue
        for clause in ct.split(","):
            if _clause_ok(clause, f, strict):
                return True
    return False
