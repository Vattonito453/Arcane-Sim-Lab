import json, glob, os, re, collections
ROOT = r"C:/Users/Vatto/Magic Rules Engine/studies"
cedh = collections.Counter(); byname = collections.Counter(); noncomp = collections.Counter()
dirs = collections.Counter()
for f in glob.glob(ROOT + "/**/*.jsonl", recursive=True):
    d = os.path.relpath(os.path.dirname(f), ROOT).replace("\\", "/")
    if d.startswith("precon"): continue
    for line in open(f, encoding="utf-8"):
        if '"combo_cast"' not in line: continue
        r = json.loads(line)
        m = re.match(r"(.*) \((\d+)/(\d+) online\)", r["detail"])
        name, k, n = m.group(1), int(m.group(2)), int(m.group(3))
        cedh["all"] += 1; dirs[d] += 1
        byname[name] += 1
        if k + 1 < n: noncomp[name] += 1
print("non-precon combo_casts:", cedh["all"])
print(dirs)
for nm in ["Thassa's Oracle", "Phyrexian Metamorph", "Hyrax Tower Scout", "Flesh Duplicate", "Clever Impersonator", "Mirrormade"]:
    print(f"{nm:22s} total={byname[nm]} noncompleting={noncomp[nm]}")
print("top non-completing:", noncomp.most_common(15))
print("sum noncompleting:", sum(noncomp.values()))
