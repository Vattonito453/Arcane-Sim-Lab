import json, collections, os
rows = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_rows.json")))
def ocat(o):
    if "Thassa's Oracle" in o and o.startswith("won"): return "WON_ORACLE"
    if "empty library" in o: return "DECKED"
    if o.startswith("won"): return "won_other"
    if o.startswith("lost"): return "lost_other"
    return "no_outcome"
def seqclass(evs):
    casts = [e for e in evs if e[2].startswith("cast")]
    ex = [e for e in casts if "Consultation" in e[2] or "Tainted Pact" in e[2]]
    orc = [e for e in casts if "Thassa's Oracle" in e[2]]
    if not ex: return "oracle_only"
    if any("TRIGGER ON STACK" in e[2] for e in ex): return "exiler_in_response_to_trigger"
    first_or = orc[0]; first_ex = ex[0]
    if first_ex[1] < first_or[1]: return "exiler_before_oracle"
    if first_ex[0] == first_or[0]: return "exiler_after_trigger_same_turn"
    return "exiler_after_trigger_later_turn"
tab = collections.Counter()
for r in rows:
    r["o"] = ocat(r["outcome"]); r["s"] = seqclass(r["events"])
    r["cc_oracle"] = any(a[1] == "combo_cast" and a[2].startswith("Thassa's Oracle") for a in r["agentlog"])
    tab[(r["agent"], r["s"], r["o"])] += 1
for k in sorted(tab): print(k, tab[k])
print()
# plan seats: all DECKED rows and all WON rows, with details
for r in rows:
    if r["agent"] == "plan" and r["o"] in ("DECKED",):
        print(r["dir"], r["file"], "g", r["game"], r["player"], r["shim"], r["s"], "cc_oracle=", r["cc_oracle"])
        print("   ", [(e[0], e[2]) for e in r["events"]])
        print("   ", [a for a in r["agentlog"] if a[1].startswith("combo")])
