"""Index Forge card scripts (res/cardsfolder/cardsfolder.zip) by card name.
Read-only. Caches a JSON index in this scratch folder."""
import json, os, re, zipfile

ZIP = r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "forge_card_index.json")


def build():
    idx = {}
    with zipfile.ZipFile(ZIP) as z:
        for n in z.namelist():
            if not n.endswith(".txt"):
                continue
            txt = z.read(n).decode("utf-8", "replace")
            # a file may hold several faces separated by ALTERNATE
            faces = re.split(r"^ALTERNATE\s*$", txt, flags=re.M)
            for i, face in enumerate(faces):
                m = re.search(r"^Name:(.*)$", face, re.M)
                if not m:
                    continue
                name = m.group(1).strip()
                idx.setdefault(name, {"file": n, "text": txt, "face": face})
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(idx, f)
    return idx


def load():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    return build()


def facts(idx, name):
    e = idx.get(name)
    if e is None and " // " in name:
        e = idx.get(name.split(" // ")[0])
    if e is None:
        return None
    t = e["text"]
    face = e["face"]
    types = (re.search(r"^Types:(.*)$", face, re.M) or [None, ""])[1]
    ab = re.findall(r"^A:AB\$ (\w+)[^\n]*", face, re.M)
    ab_nonmana = [a for a in ab if a != "Mana"]
    return {
        "types": types.strip(),
        "permanent": not re.search(r"\b(Instant|Sorcery)\b", types),
        "remAll": bool(re.search(r"^AI:RemoveDeck:All", t, re.M)),
        "remRandom": bool(re.search(r"^AI:RemoveDeck:Random", t, re.M)),
        "ailogic": sorted(set(re.findall(r"AILogic\$ ?(\w+)", t))),
        "activated": ab,
        "activated_nonmana": ab_nonmana,
        "equip": bool(re.search(r"^K:Equip", face, re.M)),
        "triggers": len(re.findall(r"^T:", face, re.M)),
        "file": e["file"],
    }


if __name__ == "__main__":
    idx = build()
    print(len(idx), "names indexed")
