#!/usr/bin/env python3
"""Summarise a JFR recording of one shim game: where CPU samples land.

Usage: jfr_summary.py <file.jfr>
Uses `jfr print --json` (JDK 17) and aggregates jdk.ExecutionSample stacks.
"""
import json, os, shutil, subprocess, sys, collections, re

JFR = os.environ.get("JFR_BIN") or shutil.which("jfr") or "/opt/homebrew/opt/openjdk@17/bin/jfr"
path = sys.argv[1]

def events(name):
    out = subprocess.run([JFR, "print", "--json", "--stack-depth", "1024", "--events", name, path],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    return data["recording"]["events"]

samples = events("jdk.ExecutionSample")
print(f"execution samples: {len(samples)}")

def frames(ev):
    st = ev["values"].get("stackTrace") or {}
    out = []
    for f in st.get("frames", []):
        m = f.get("method") or {}
        t = ((m.get("type") or {}).get("name") or "?").replace("/", ".")
        out.append(f"{t}.{m.get('name','?')}")
    return out

def bucket(cls):
    if cls.startswith("simlab.shim"): return "shim (our Java)"
    if cls.startswith("forge.ai.simulation"): return "forge.ai.simulation"
    if cls.startswith("forge.ai"): return "forge.ai (stock AI)"
    if cls.startswith("forge.game.combat"): return "forge.game.combat"
    if cls.startswith("forge.game.staticability") or cls.startswith("forge.game.replacement") or cls.startswith("forge.game.trigger"):
        return "forge.game static/replacement/trigger"
    if cls.startswith("forge.game"): return "forge.game (rules engine, other)"
    if cls.startswith("forge."): return "forge (other)"
    if cls.startswith("java.awt") or cls.startswith("sun.awt") or cls.startswith("sun.java2d") or cls.startswith("javax.swing"): return "AWT/Swing"
    if cls.startswith("java.") or cls.startswith("jdk.") or cls.startswith("sun."): return "JDK"
    if cls.startswith("com.google.common"): return "guava"
    return "other: " + cls.split(".")[0]

self_top = collections.Counter()
self_bucket = collections.Counter()
incl_bucket = collections.Counter()   # sample counted once per bucket present anywhere in stack
incl_method = collections.Counter()   # once per distinct method present in stack
thread_ct = collections.Counter()
by_ai_entry = collections.Counter()
by_ai_owner = collections.Counter()
no_ai = collections.Counter()
combat_ai = 0; shim_combat = 0; mana = 0; sim_ai = 0; canblock = 0; static_layer = 0
for ev in samples:
    fr = frames(ev)
    if not fr: continue
    thread_ct[(ev["values"].get("sampledThread") or {}).get("javaName", "?")] += 1
    top = fr[0]
    self_top[top] += 1
    self_bucket[bucket(top)] += 1
    seen = set()
    for f in fr:
        b = bucket(f)
        if b not in seen:
            incl_bucket[b] += 1; seen.add(b)
    for f in set(fr):
        incl_method[f] += 1
    joined = " ".join(fr)
    if "forge.ai.AiAttackController" in joined or "forge.ai.AiBlockController" in joined: combat_ai += 1
    if "simlab.shim.PlanPlayerController.humanize" in joined or "simlab.shim.PlanPlayerController.holdBack" in joined or "simlab.shim.PlanPlayerController.preferOpen" in joined or "simlab.shim.PlanPlayerController.kingmaker" in joined: shim_combat += 1
    if "forge.ai.ComputerUtilMana" in joined: mana += 1
    if "forge.ai.simulation" in joined: sim_ai += 1
    if "forge.game.combat.CombatUtil.canBlock" in joined: canblock += 1
    if "forge.game.staticability" in joined: static_layer += 1
    # entry point into the AI: the deepest forge.ai frame (closest to the bottom)
    ai_frames = [f for f in fr if f.startswith("forge.ai.") or f.startswith("simlab.shim.")]
    th = (ev["values"].get("sampledThread") or {}).get("javaName", "?")
    if ai_frames:
        by_ai_entry[ai_frames[-1]] += 1
        # the SHALLOWEST ai frame = the AI routine that owns the work
        by_ai_owner[(th, ai_frames[0])] += 1
    else:
        no_ai[th] += 1

n = len(samples) or 1
def pct(x): return f"{100*x/n:5.1f}%"
print("\n-- threads --")
for t, c in thread_ct.most_common(6): print(f"  {pct(c)} {t}")
print("\n-- SELF time by bucket (top frame) --")
for b, c in self_bucket.most_common(12): print(f"  {pct(c)} {b}")
print("\n-- INCLUSIVE by bucket (any frame in stack) --")
for b, c in incl_bucket.most_common(14): print(f"  {pct(c)} {b}")
print("\n-- specific inclusive markers --")
print(f"  {pct(combat_ai)} stock AI combat (AiAttackController/AiBlockController)")
print(f"  {pct(shim_combat)} shim humanize* / holdBack / preferOpen / kingmaker passes")
print(f"  {pct(canblock)} CombatUtil.canBlock anywhere in stack")
print(f"  {pct(mana)} ComputerUtilMana anywhere in stack")
print(f"  {pct(sim_ai)} forge.ai.simulation (lookahead)")
print(f"  {pct(static_layer)} forge.game.staticability (layer engine)")
print("\n-- top AI/shim entry points (deepest ai/shim frame) --")
for m, c in by_ai_entry.most_common(15): print(f"  {pct(c)} {m}")
print("\n-- samples with NO forge.ai/shim frame at all (pure rules engine / logging), by thread --")
for t, c in no_ai.most_common(4): print(f"  {pct(c)} {t}")
print("\n-- AI routine owning the work (shallowest ai/shim frame), by thread --")
for (t, m), c in by_ai_owner.most_common(18): print(f"  {pct(c)} [{t}] {m}")
print("\n-- top INCLUSIVE methods (excluding pure plumbing) --")
skip = re.compile(r"^(java\.|jdk\.|sun\.|com\.google)")
shown = 0
for m, c in incl_method.most_common(400):
    if skip.match(m): continue
    print(f"  {pct(c)} {m}"); shown += 1
    if shown >= 40: break
print("\n-- top SELF methods --")
for m, c in self_top.most_common(20): print(f"  {pct(c)} {m}")

# GC + heap
try:
    gcs = events("jdk.GarbageCollection")
    print(f"\n-- GC -- collections: {len(gcs)}")
    pauses = []
    for e in gcs:
        v = e["values"].get("sumOfPauses")
        if isinstance(v, str):
            m = re.match(r"PT(?:(\d+)M)?([\d.]+)S", v)
            if m: pauses.append((int(m.group(1) or 0)*60 + float(m.group(2)))*1000)
    if pauses: print(f"  total pause {sum(pauses)/1000:.2f} s, max pause {max(pauses):.0f} ms")
    hs = events("jdk.GCHeapSummary")
    used = [int(e["values"]["heapUsed"]) for e in hs if "heapUsed" in e["values"]]
    if used: print(f"  heapUsed peak {max(used)/2**30:.2f} GiB")
except Exception as ex:
    print("gc summary failed:", ex)
