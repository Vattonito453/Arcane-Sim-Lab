"""Adapt raw shim JSONL cells into one result per pod (read-only on repo),
run analysis.analyse, and dump per-combo per-game detail vs actual win method."""
import sys, json, glob, os, re, collections
from pathlib import Path
sys.path.insert(0, r"C:/Users/Vatto/Magic Rules Engine/engine")
import shim_log_adapter, analysis

def load_pod(files):
    games = []; meta = None
    for f in sorted(files):
        text = open(f, encoding="utf-8", errors="replace").read()
        r = shim_log_adapter.parse_shim_jsonl(text, source=f)
        m = r.get("meta") or {}
        # keep the raw meta record's decks
        for line in text.splitlines()[:3]:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("rec") == "meta":
                m["_raw"] = rec
                break
        if meta is None: meta = m
        for g in r.get("games") or []:
            g["_src"] = os.path.basename(f)
            g["_agents"] = (m.get("_raw") or {}).get("agents")
            g["_players"] = (m.get("_raw") or {}).get("players")
        games += r.get("games") or []
    return meta, games

def main(pattern, out_json):
    files = glob.glob(pattern)
    by_pod = collections.defaultdict(list)
    for f in files:
        mm = re.search(r"(n7WpsqsZtdQ|2iA_Jt0d6sM|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)", f)
        if mm: by_pod[mm.group(1)].append(f)
    out = {}
    for pod, fs in sorted(by_pod.items()):
        meta, games = load_pod(fs)
        raw = meta.get("_raw") or {}
        decks = [Path(d).name for d in raw.get("decks") or []]
        deck_dir = Path(r"C:/Users/Vatto/Magic Rules Engine/studies/human_ceiling/decks") / pod / "dck"
        result = {"meta": {"decks": decks, "source": "rotated", "humanized": raw.get("humanized"), "agent": "shim"}, "games": games, "file": pod}
        rep = analysis.analyse(result, deck_dirs=[deck_dir], fetch=False)
        out[pod] = {"n_games": len(games), "methods": rep["summary"]["methods"], "decks": {}, "games": rep["games"],
                    "agents": [(g["_src"], g["_agents"], g["_players"]) for g in games[:1]]}
        for name, d in rep["decks"].items():
            out[pod]["decks"][name] = [dict({k: c[k] for k in ("cards","produces","assembled_games","converted_games","games_played","reading","idle_online_turns","expected_drawn_games","median_assembled_turn")}, games=[g for g in c["games"] if g["assembled_turn"] is not None]) for c in d["combos"]]
        # also dump adapted games for later hand-checks
        if "--keep" in sys.argv: json.dump(result, open(out_json.replace(".json", f"_{pod}_result.json"), "w", encoding="utf-8"))
    json.dump(out, open(out_json, "w", encoding="utf-8"), indent=1)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
