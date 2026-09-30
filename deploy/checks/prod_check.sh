#!/usr/bin/env bash
# Read-only production check (tasks/25-repair-plan.md, WS0 task 3).
#
# Copy to the VM and run there (inline commands over gcloud ssh get mangled by
# PowerShell; see memory note "gcloud ssh needs script files"):
#   gcloud compute scp deploy/checks/prod_check.sh simlab:/tmp/prod_check.sh --zone=us-central1-a
#   gcloud compute ssh simlab --zone=us-central1-a --command="bash /tmp/prod_check.sh"
#
# It writes nothing outside /tmp. The record_run reproduction runs in the
# WORKER container (where the post-run hook runs, inside Engine.simulate)
# against COPIES of /data/plan_feedback.json and /data/card_cache.json.
set -u

section() { printf '\n## %s\n' "$1"; }

section "time and host"
date -u; hostname

section "containers"
sudo docker ps --format '{{.Names}}  {{.Status}}  {{.Image}}'

section "preflight (api container)"
sudo docker exec deploy-api-1 python3 /app/deploy/preflight.py --files 2>&1 | tail -45

section "preflight image half (worker container; R1.1 and later)"
sudo docker exec deploy-worker-1 sh -c 'test -f /app/deploy/preflight.py && python3 /app/deploy/preflight.py --image-only 2>&1 | tail -25 || echo "no preflight in this worker image (before R1.1)"'

section "QA layer A (qa.json per run, review queue counts)"
sudo docker exec deploy-worker-1 sh -c 'r=$(ls /data/sim_results/sim_*.json 2>/dev/null | wc -l); q=$(ls /data/simkb/runs/*/qa.json 2>/dev/null | wc -l); echo "results: $r  with qa.json: $q"; echo "auto queue: $(ls /data/simkb/review_queue/auto 2>/dev/null | wc -l)  human queue: $(ls /data/simkb/review_queue/human 2>/dev/null | wc -l)"'
sudo docker logs deploy-worker-1 2>&1 | grep -E "QA (started|killed|gave up|not started)|QA sweep failed" | tail -10 || true

section "shim version and commit (worker container)"
sudo docker logs deploy-worker-1 2>&1 | grep -m1 'shim commit' || echo "no 'shim commit' line in worker log"
sudo docker exec deploy-worker-1 sh -c 'ls -la /opt/simlab-forge-shim 2>/dev/null; cat /opt/simlab-forge-shim/COMMIT 2>/dev/null || echo "no COMMIT file"'

section "repo on the VM"
for d in /home/*/simlab; do [ -d "$d/.git" ] && echo "$d: $(git -C "$d" log --oneline -1)"; done

section "environment of interest (worker)"
sudo docker exec deploy-worker-1 sh -c 'env | grep -E "^MTG_(DATA_DIR|PLAN_FEEDBACK_APPLY|EMBEDDED_WORKER|OFFLINE)=" || true'

section "plan_feedback.json summary"
cat > /tmp/pf_summary.py <<'PY'
import json, os, time
p = "/data/plan_feedback.json"
try:
    st = os.stat(p)
    print("path", p, "size", st.st_size, "mtime", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(st.st_mtime)), "UTC")
    s = json.load(open(p, encoding="utf-8"))
except FileNotFoundError:
    print("missing:", p); raise SystemExit(0)
print("top-level keys:", sorted(s.keys()))
print("_runs present:", "_runs" in s, "count:", len(s.get("_runs") or []))
decks = s.get("decks") or {}
print("decks:", len(decks))
for name, d in sorted(decks.items())[:60]:
    print("  %-40s games=%s wins=%s methods=%s" % (name[:40], d.get("games"), d.get("wins"), d.get("methods")))
tags = s.get("tags") or {}
print("tags:", len(tags), {k: (v.get("games") if isinstance(v, dict) else v) for k, v in list(tags.items())[:20]})
PY
sudo docker cp /tmp/pf_summary.py deploy-worker-1:/tmp/pf_summary.py
sudo docker exec deploy-worker-1 python3 /tmp/pf_summary.py

section "decks carrying ' // ' names"
sudo docker exec deploy-worker-1 sh -c 'n=$(grep -l " // " /data/decks/*.dck 2>/dev/null | wc -l); echo "files with // : $n of $(ls /data/decks/*.dck 2>/dev/null | wc -l)"; grep -H " // " /data/decks/*.dck 2>/dev/null | head -40'

section "record_run reproduction in the worker container (against copies)"
cat > /tmp/pf_repro.py <<'PY'
import glob, json, os, shutil, sys, traceback
scratch = "/tmp/pfcheck"
shutil.rmtree(scratch, ignore_errors=True)
os.makedirs(scratch)
for f in ("plan_feedback.json", "card_cache.json", "combo_cache.json"):
    src = os.path.join("/data", f)
    if os.path.exists(src):
        shutil.copy(src, scratch)
os.environ["MTG_DATA_DIR"] = scratch   # redirect every store read/write to the copy
sys.path.insert(0, "/app/engine")
results = sorted(glob.glob("/data/sim_results/sim_*.json"), key=os.path.getmtime)
print("result files:", len(results))
if not results:
    raise SystemExit(0)
newest = results[-1]
print("newest:", newest)
payload = json.load(open(newest, encoding="utf-8"))
try:
    import plan_feedback
    print("plan_feedback module:", plan_feedback.__file__)
    print("store path used:", plan_feedback._store_path())
    store = plan_feedback.record_run(payload)
    decks = store.get("decks") or {}
    print("COMPLETED. decks now:", len(decks), "_runs:", len(store.get("_runs") or []))
    print("sample:", {k: decks[k].get("games") for k in list(decks)[:6]})
except Exception:
    print("RAISED:")
    traceback.print_exc(file=sys.stdout)
PY
sudo docker cp /tmp/pf_repro.py deploy-worker-1:/tmp/pf_repro.py
sudo docker exec deploy-worker-1 python3 /tmp/pf_repro.py
sudo docker exec deploy-worker-1 rm -rf /tmp/pfcheck /tmp/pf_repro.py /tmp/pf_summary.py

section "done"
