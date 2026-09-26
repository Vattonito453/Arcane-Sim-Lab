"""Independent re-check of combo_execution/ui_labels_unexecuted_lines_as_fired.

Runs the PRODUCT's own engine/analysis.analyse() (the code that sets
combo["reading"] = "fired") over adapted shim runs, then asks, for every
converted (assembled-then-won) game, whether any evidence of the line being
executed exists in the log.
"""
import collections, glob, json, os, re, sys, zipfile
from pathlib import Path

ENGINE = "C:/Users/Vatto/Magic Rules Engine/engine"
S = "C:/Users/Vatto/Magic Rules Engine/studies/"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE)
import analysis  # noqa
import shim_log_adapter  # noqa
import cards  # noqa

# ---------- Forge RemoveDeck:All index (read-only from the zip) ----------
REM = {}
z = zipfile.ZipFile("C:/Users/Vatto/forge/res/cardsfolder/cardsfolder.zip")
for n in z.namelist():
    if not n.endswith(".txt"):
        continue
    txt = z.read(n).decode("utf-8", "replace")
    names = re.findall(r"^Name:(.+)$", txt, re.M)
    rem = bool(re.search(r"^AI:RemoveDeck:All", txt, re.M))
    for nm in names:
        REM[nm.strip().lower()] = REM.get(nm.strip().lower(), False) or rem


def is_rem(card):
    return REM.get(card.lower()) or REM.get(card.split(" // ")[0].lower(), False)


# ---------- run groups ----------
POD_RE = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")


def groups():
    out = []
    for arm in ["agent_viability/runs_015_default", "agent_viability/runs_winmax",
                "agent_viability/runs_016_engine"]:
        for pod in ["2iA_Jt0d6sM", "n7WpsqsZtdQ"]:
            out.append((arm, pod, sorted(glob.glob(S + f"{arm}/cell_{pod}_rot*.jsonl"))))
    for pod in ["2iA_Jt0d6sM", "n7WpsqsZtdQ", "5A6o18Bra0Y", "B421mac67IE", "Bq-nFi0f1jA",
                "CxKMqO36DdM", "OuY6mdiXbHU", "sZA0KqXCGrY"]:
        fs = sorted(glob.glob(S + f"human_ceiling/runs/shim_raw_hc_*{pod}_rot*.jsonl"))
        out.append(("human_ceiling/runs", pod, fs))
    ship = collections.defaultdict(list)
    for f in sorted(glob.glob(S + "behavior_rubric/runs_agent_shipping/*.jsonl")):
        m = POD_RE.search(os.path.basename(f))
        ship[m.group(1) if m else "?"].append(f)
    for pod, fs in ship.items():
        out.append(("behavior_rubric/runs_agent_shipping", pod, fs))
    out.append(("tutor_targeting/runs_stock", "n7WpsqsZtdQ",
                sorted(glob.glob(S + "tutor_targeting/runs_stock/shim_raw_*.jsonl"))))
    out.append(("tutor_targeting/runs_stage2", "n7WpsqsZtdQ",
                sorted(glob.glob(S + "tutor_targeting/runs_stage2/shim_raw_*.jsonl"))))
    return [g for g in out if g[2]]


ACT = re.compile(r"^(Ai\(\d+\)-\S+) (activated|triggered|cast) (.+?)(?: targeting .*)?$")


def load_group(files):
    games, agents_by_game, meta0 = [], [], None
    for f in files:
        text = open(f, encoding="utf-8", errors="replace").read()
        meta = None
        for line in text.splitlines():
            if line.startswith('{"rec":"meta"'):
                meta = json.loads(line)
                break
        res = shim_log_adapter.parse_shim_jsonl(text, source=f)
        if meta0 is None:
            meta0 = dict(res.get("meta") or {})
            meta0["decks"] = [d.replace("\\", "/") for d in (meta or {}).get("decks") or []]
            # adapter keeps the deck list; make sure filenames resolve
        amap = {}
        if meta:
            for p, a in zip(meta.get("players") or [], meta.get("agents") or []):
                amap[p] = a
        for g in res.get("games") or []:
            games.append(g)
            agents_by_game.append(amap)
    result = {"meta": dict(meta0, decks=[Path(d).name for d in (meta0.get("decks") or [])]),
              "games": games, "file": "merged"}
    return result, agents_by_game


def main():
    rows = []           # one per (group, deck, combo)
    conv_rows = []      # one per converted (group, deck, combo, game)
    asm_rows = []
    for arm, pod, files in groups():
        result, agmap = load_group(files)
        deck_dirs = [Path(S + f"human_ceiling/decks/{pod}/dck")]
        rep = analysis.analyse(result, deck_dirs=deck_dirs, fetch=False)
        for name, d in rep["decks"].items():
            for c in d["combos"]:
                rem_pieces = [p for p in c["cards"] if is_rem(p)]
                rows.append({"arm": arm, "pod": pod, "deck": name, "line": " + ".join(c["cards"]),
                             "reading": c.get("reading"), "assembled": c["assembled_games"],
                             "converted": c["converted_games"], "played": c["games_played"],
                             "rem": rem_pieces})
                for gi in c["games"]:
                    if gi["assembled_turn"] is not None:
                        _g = result["games"][gi["n"] - 1]
                        _k = next((k for k in _g["players"] if analysis._bare(k) == name), None)
                        asm_rows.append({"arm": arm, "pod": pod, "deck": name, "line": " + ".join(c["cards"]),
                                         "n": gi["n"], "agent": agmap[gi["n"] - 1].get(_k, "?"),
                                         "won": gi["won"], "rem": bool(rem_pieces),
                                         "method": rep["games"][gi["n"] - 1]["method"]})
                    if gi["assembled_turn"] is None or not gi["won"]:
                        continue
                    n = gi["n"]
                    game = result["games"][n - 1]
                    key = next((k for k in game["players"] if analysis._bare(k) == name), None)
                    agent = agmap[n - 1].get(key, "?")
                    method = rep["games"][n - 1]
                    pieces = {analysis._norm(p) for p in c["cards"]}
                    per_turn = collections.Counter()
                    activated = 0
                    own_turns_after = 0
                    won_turn = game["turns"][-1]["turn"] if game["turns"] else 0
                    for t in game["turns"]:
                        tn = t["turn"]
                        if tn > gi["assembled_turn"] and t.get("active_player") == key:
                            own_turns_after += 1
                        if tn < gi["assembled_turn"]:
                            continue
                        for e in t["events"]:
                            if e.get("action") != "stack_add":
                                continue
                            m = ACT.match(e.get("raw", ""))
                            if not m or m.group(1) != key:
                                continue
                            obj = cards.normalize_name(m.group(3)).lower()
                            if obj in pieces:
                                per_turn[tn] += 1
                                if m.group(2) == "activated":
                                    activated += 1
                    mx = max(per_turn.values()) if per_turn else 0
                    spell = method["method"] == "spell"
                    conv_rows.append({
                        "arm": arm, "pod": pod, "deck": name, "line": " + ".join(c["cards"]),
                        "agent": agent, "n": n, "assembled_turn": gi["assembled_turn"],
                        "end_turn": won_turn, "own_turns_after": own_turns_after,
                        "method": method["method"], "detail": method.get("detail", "")[:80],
                        "max_piece_stack_per_turn": mx, "piece_activations": activated,
                        "rem": bool(rem_pieces)})
    json.dump({"rows": rows, "conv": conv_rows, "asm": asm_rows}, open(os.path.join(HERE, "out.json"), "w"), indent=1)

    # ---- summaries ----
    fired = [r for r in rows if r["reading"] == "fired"]
    print("combo rows (group x deck x line):", len(rows))
    print("readings:", collections.Counter(r["reading"] for r in rows))
    print("converted (assembled-then-won) game instances:", len(conv_rows))
    print("win methods of converted instances:", collections.Counter(c["method"] for c in conv_rows))

    def ev(c, thr=5):
        return c["method"] == "spell" or c["max_piece_stack_per_turn"] >= thr

    print("instances with no execution evidence (>=5 piece stack items in a turn, or spell win):",
          sum(1 for c in conv_rows if not ev(c)), "of", len(conv_rows))
    print("instances with no execution evidence (>=3):", sum(1 for c in conv_rows if not ev(c, 3)))
    print("instances with zero piece activations after assembly:",
          sum(1 for c in conv_rows if c["piece_activations"] == 0))
    print("instances where win came > 1 own turn after assembly:",
          sum(1 for c in conv_rows if c["own_turns_after"] > 1))
    # per fired reading: any converted game with evidence?
    byline = collections.defaultdict(list)
    for c in conv_rows:
        byline[(c["arm"], c["pod"], c["deck"], c["line"])].append(c)
    nf_noev = 0
    for r in fired:
        cs = byline[(r["arm"], r["pod"], r["deck"], r["line"])]
        if not any(ev(c) for c in cs):
            nf_noev += 1
    print(f"'fired' readings: {len(fired)}; of which NO converted game shows evidence: {nf_noev}")
    # RemoveDeck:All subset
    remc = [c for c in conv_rows if c["rem"]]
    print("\nRemoveDeck:All lines: converted instances", len(remc),
          "methods", collections.Counter(c["method"] for c in remc))
    print("  of which zero activations of a piece:", sum(1 for c in remc if c["piece_activations"] == 0))
    remfired = [r for r in fired if r["rem"]]
    print("  fired readings on RemoveDeck:All lines:", len(remfired))
    print("  assembled games on RemoveDeck:All lines:", sum(r["assembled"] for r in rows if r["rem"]),
          "converted:", sum(r["converted"] for r in rows if r["rem"]))
    # seat-game level
    seat = collections.defaultdict(bool)
    for c in conv_rows:
        k = (c["arm"], c["pod"], c["n"], c["deck"])
        seat[k] = seat[k] or ev(c)
    print("\nseat-games counted converted:", len(seat), "; with no evidence on any line:",
          sum(1 for v in seat.values() if not v))


if __name__ == "__main__":
    main()
