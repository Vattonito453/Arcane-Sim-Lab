import zipfile, json, re
z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
flags = {}
for info in z.infolist():
    if not info.filename.endswith(".txt"): continue
    t = z.read(info).decode("utf-8", "replace")
    names = re.findall(r"^Name:(.+)$", t, re.M)
    rd = re.findall(r"^AI:RemoveDeck:(\w+)", t, re.M)
    logic = re.findall(r"AILogic\$ ?(\w+)", t)
    if not names: continue
    full = " // ".join(n.strip() for n in names)
    rec = {"removeDeck": rd, "ailogic": sorted(set(logic))}
    for n in [full] + [n.strip() for n in names]:
        flags.setdefault(n, rec)
json.dump(flags, open("forge_flags.json", "w"))
print(len(flags), "names indexed")
