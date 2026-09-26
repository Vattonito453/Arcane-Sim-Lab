import os, re, collections, json
root = r"C:/Users/Vatto/Magic Rules Engine/studies"
rng = {}
shim = {}
for dp, dn, fn in os.walk(root):
    for f in fn:
        if not f.endswith(".jsonl"): continue
        rel = os.path.relpath(dp, root).replace("\\", "/")
        m = re.search(r"(2026\d{4})", f)
        d = m.group(1) if m else None
        if d is None:
            import time
            d = time.strftime("%Y%m%d", time.localtime(os.path.getmtime(os.path.join(dp,f))))+"m"
        lo, hi = rng.get(rel, (d, d))
        rng[rel] = (min(lo, d), max(hi, d))
        if rel not in shim:
            with open(os.path.join(dp,f), encoding="utf-8", errors="replace") as fh:
                first = fh.readline()
            try:
                shim[rel] = json.loads(first).get("shim")
            except Exception:
                shim[rel] = "?"
for k in sorted(rng):
    print(f"{rng[k][0]}..{rng[k][1]}  shim={shim.get(k)}  {k}")
