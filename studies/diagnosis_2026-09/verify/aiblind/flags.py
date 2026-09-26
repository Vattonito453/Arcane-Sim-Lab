import zipfile, json, re, collections
z = zipfile.ZipFile(r"C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
names = [n for n in z.namelist() if n.endswith('.txt')]
flag_all = {}; flag_rand = 0; total=0
name2flags = {}
for n in names:
    total += 1
    t = z.read(n).decode('utf-8','replace')
    flags = set(re.findall(r'^AI:RemoveDeck:(\w+)', t, re.M))
    # card names: Name: lines (multi-face)
    cn = re.findall(r'^Name:(.*)$', t, re.M)
    for c in cn:
        name2flags[c.strip()] = sorted(flags)
    if 'All' in flags: flag_all[n]=cn
    if 'Random' in flags: flag_rand += 1
print("scripts", total, "flag All", len(flag_all), "Random", flag_rand)
json.dump(name2flags, open('name2flags.json','w'))
