import json, glob, re, collections
R = r"C:/Users/Vatto/Magic Rules Engine/studies"
files = glob.glob(R + "/**/*.jsonl", recursive=True)
steer_over_portal = collections.Counter(); steer_to_portal = 0; arms = collections.Counter()
modes = collections.Counter(); all_steers_magda = 0
search_seen_portal = 0; ss_examples = []
for f in files:
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if "Portal to Phyrexia" not in line: continue
            try: r = json.loads(line)
            except: continue
            if r.get("rec") != "agent": continue
            d = r.get("detail", "")
            if r["event"] == "tutor_steer":
                m = re.search(r"mode=(\w+).*steer=(.+?) over=(.+)$", d)
                if m and m.group(3) == "Portal to Phyrexia":
                    steer_over_portal[(m.group(1), m.group(2))] += 1
                    arms[f.split("studies\\")[1].split("\\")[0] + "/" + f.split("\\")[-2]] += 1
                if m and m.group(2) == "Portal to Phyrexia": steer_to_portal += 1
            elif r["event"] == "search_seen":
                search_seen_portal += 1
                if len(ss_examples) < 3: ss_examples.append(d[:300])
print("tutor_steer choosing something OVER Portal to Phyrexia:", sum(steer_over_portal.values()))
for k, v in steer_over_portal.most_common(): print("   ", v, k)
print("tutor_steer choosing Portal:", steer_to_portal)
print("by arm:", arms.most_common())
print("search_seen events listing Portal:", search_seen_portal)
for e in ss_examples: print("   ", e)
