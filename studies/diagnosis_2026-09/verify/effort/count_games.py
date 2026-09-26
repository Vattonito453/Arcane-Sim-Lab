import os, sys, collections, json
root = r"C:/Users/Vatto/Magic Rules Engine/studies"
cnt = collections.Counter()
files = collections.Counter()
for dp, dn, fn in os.walk(root):
    for f in fn:
        if not f.endswith(".jsonl"): continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(dp, root).replace("\\", "/")
        n = 0
        with open(p, "rb") as fh:
            for line in fh:
                if line.startswith(b'{"rec":"result"'):
                    n += 1
        cnt[rel] += n
        files[rel] += 1
tot = 0
for k in sorted(cnt):
    print(f"{cnt[k]:6d} games {files[k]:5d} files  {k}")
    tot += cnt[k]
print("TOTAL", tot)
