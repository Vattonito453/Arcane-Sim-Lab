"""Own index: card name -> flags from Forge cardsfolder.zip (AI:RemoveDeck:All etc)."""
import zipfile, re, json, os
ZIP = r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip"
HERE = os.path.dirname(os.path.abspath(__file__))
C = os.path.join(HERE, "remidx.json")
def build():
    out = {}
    with zipfile.ZipFile(ZIP) as z:
        for n in z.namelist():
            if not n.endswith(".txt"): continue
            t = z.read(n).decode("utf-8", "replace")
            names = [m.strip() for m in re.findall(r"^Name:(.*)$", t, re.M)]
            flags = {"remAll": bool(re.search(r"^AI:RemoveDeck:All\s*$", t, re.M)),
                     "remRandom": bool(re.search(r"^AI:RemoveDeck:Random\s*$", t, re.M)),
                     "never": bool(re.search(r"AILogic\$ ?Never", t)),
                     "types": [m.strip() for m in re.findall(r"^Types:(.*)$", t, re.M)],
                     "ab": re.findall(r"^A:AB\$ (\w+)", t, re.M),
                     "sp": bool(re.search(r"^A:SP\$", t, re.M))}
            for nm in names:
                out.setdefault(nm, flags)
            if len(names) > 1:
                out.setdefault(" // ".join(names), flags)
    json.dump(out, open(C, "w"))
    return out
def load():
    return json.load(open(C)) if os.path.exists(C) else build()
if __name__ == "__main__":
    d = build()
    print(len(d), "names;", sum(v["remAll"] for v in d.values()), "remAll")
