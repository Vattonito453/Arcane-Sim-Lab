"""Per-tutor-cast extraction from raw shim JSONL.

For every tutor (broad census set + plan.tutors) cast or activated by any seat:
drawn turn, cast turn/round/phase, own turn or not, decider (tutor_cast event
= shim, else stock AI), what the search offered (search_seen, plan seats
only), what was taken (steer > picked; stock seats inferred from zone moves),
whether the taken card was later cast/put onto battlefield, whether it is a
line piece, and whether the seat won.

Usage: py parse_tutors.py <arm_label> <plans.json or 'auto'> <glob>...
Writes rows_<arm>.json next to this file.
"""
import json, re, sys, glob, collections
from pathlib import Path

HERE = Path(__file__).parent
census = json.load(open(HERE / "census.json"))
TUTORS = set()
for deck, res in census.items():
    for n, c in res.items():
        if c["broad"]:
            TUTORS.add(n)
# lands that tutor (Urza's Saga) are kept but flagged
TOP_TUTORS = {"Vampiric Tutor", "Imperial Seal", "Mystical Tutor", "Enlightened Tutor",
              "Worldly Tutor", "Personal Tutor", "Sylvan Tutor", "Scheming Symmetry",
              "Idyllic Tutor"}  # Idyllic goes to hand actually; keep separate below
TOP_TUTORS.discard("Idyllic Tutor")

def rnd(turn, seats):
    if turn is None or turn < 1:
        return 0
    return (turn - 1) // seats + 1

def load_plans(path):
    if not path or path == "none":
        return {}
    p = json.load(open(path, encoding="utf-8"))
    return p.get("decks", p)

def deck_of(player):
    return re.sub(r"^Ai\(\d+\)-", "", player)

def parse_file(fn, plans_for_file):
    games = collections.defaultdict(lambda: {"entries": [], "zones": [], "agent": [], "result": None})
    meta = None
    for line in open(fn, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        rec = r.get("rec")
        if rec == "meta":
            meta = r
            continue
        g = r.get("game")
        if rec == "entry":
            games[g]["entries"].append(r)
        elif rec == "zone":
            games[g]["zones"].append(r)
        elif rec == "agent":
            games[g]["agent"].append(r)
        elif rec == "result":
            games[g]["result"] = r
    if meta is None:
        return []
    players = meta["players"]
    agents = dict(zip(players, meta.get("agents", ["?"] * len(players))))
    seats = len(players)
    plans = plans_for_file
    for gi, G in sorted(games.items(), key=lambda kv: (kv[0] is None, kv[0])):
        res = G["result"]
        if res is None:
            continue
        winner = res.get("winner")
        win_turn = res.get("turns")
        # activated-tutor STACK_ADD entries with a derived turn number
        turn = 0
        acts = []  # (turn, player, card)
        for e in G["entries"]:
            if e["type"] == "TURN":
                m = re.match(r"Turn (\d+)", e["message"])
                if m:
                    turn = int(m.group(1))
            elif e["type"] == "STACK_ADD":
                m = re.match(r"(Ai\(\d+\)-[^ ]+) activated (.+?)(?: targeting .*)?$", e["message"])
                if m and m.group(2) in TUTORS:
                    acts.append((turn, m.group(1), m.group(2)))
        agent_by = collections.defaultdict(list)
        for a in G["agent"]:
            agent_by[(a["player"], a["event"])].append(a)
        # search_seen parse
        seen = collections.defaultdict(list)  # player -> list of dicts
        steers = {}
        for p in players:
            for a in agent_by.get((p, "search_seen"), []):
                d = a["detail"]
                kv = dict(re.findall(r"(\w+)=([^ ]+)", d.split(" missing=")[0]))
                tail = d.split(" missing=")[1] if " missing=" in d else ""
                m = re.match(r"(.*?) picked=(.*?) planPick=(.*?) src=(.*)$", tail)
                if m:
                    kv["missing"], kv["picked"], kv["planPick"], kv["src"] = m.groups()
                kv["turn"] = a["turn"]
                seen[p].append(kv)
            for a in agent_by.get((p, "tutor_steer"), []):
                d = a["detail"]
                m = re.match(r"sid=(\d+) mode=(\w+) value=(-?\d+) stockValue=(-?\d+) steer=(.*) over=(.*)$", d)
                if m:
                    steers[(p, int(m.group(1)))] = {"mode": m.group(2), "value": int(m.group(3)),
                                                    "stockValue": int(m.group(4)),
                                                    "steer": m.group(5), "over": m.group(6)}
        tcast = collections.defaultdict(list)
        for p in players:
            for a in agent_by.get((p, "tutor_cast"), []):
                m = re.match(r"(.*) seeking (.*)$", a["detail"])
                if m:
                    tcast[p].append((a["turn"], m.group(1), m.group(2)))
        Z = G["zones"]
        # first arrival in hand per cardId
        arrive = {}
        for z in Z:
            if z["to"] == "Hand" and z["cardId"] not in arrive:
                arrive[z["cardId"]] = z.get("turn")
        # card fates per (player, name): list of (idx, turn, from, to)
        fates = collections.defaultdict(list)
        for i, z in enumerate(Z):
            owner = z.get("toPlayer") or z.get("fromPlayer")
            fates[(owner, z["card"])].append((i, z.get("turn"), z["from"], z["to"], z.get("phase", "")))
        used_seen = set()
        rows = []
        def mk_row(p, name, cast_turn, phase, kind, zi):
            deck = deck_of(p)
            plan = plans.get(deck, {}) if plans else {}
            lines = [set(l["cards"]) for l in plan.get("lines", [])]
            line_cards = set().union(*lines) if lines else set()
            targets = plan.get("search", {}).get("targets", {})
            row = {"file": Path(fn).name, "shim": meta.get("shim"), "game": gi, "player": p,
                   "deck": deck, "agent": agents.get(p), "tutor": name, "kind": kind,
                   "cast_turn": cast_turn, "cast_round": rnd(cast_turn, seats), "phase": phase,
                   "own_turn": None, "winner": winner == p, "game_winner": winner,
                   "game_turns": win_turn, "timed_out": res.get("timedOut"),
                   "in_plan_tutors": name in set(plan.get("tutors", [])) if plan else None}
            # whose turn: the zone record turn -> active player index = (turn-1) % seats in seat order?
            # Forge seats rotate from a random/first player; derive from TURN entries instead
            return row
        # whose turn map from entries
        whose = {}
        for e in G["entries"]:
            if e["type"] == "TURN":
                m = re.match(r"Turn (\d+) \((.+)\)", e["message"])
                if m:
                    whose[int(m.group(1))] = m.group(2)
        # --- spell / permanent casts (Hand->Stack or Command->Stack)
        for i, z in enumerate(Z):
            if z["card"] not in TUTORS:
                continue
            if z["from"] in ("Hand", "Command", "Exile", "Graveyard") and z["to"] == "Stack":
                p = z["fromPlayer"]
                name = z["card"]
                row = mk_row(p, name, z.get("turn"), z.get("phase", ""), "cast", i)
                row["drawn_turn"] = arrive.get(z["cardId"])
                row["from_zone"] = z["from"]
                rows.append((row, i, z["cardId"]))
        # --- activations
        for (t, p, name) in acts:
            row = mk_row(p, name, t, "", "activated", None)
            row["drawn_turn"] = None
            row["from_zone"] = "ability"
            rows.append((row, None, None))
        out = []
        for row, zi, cid in rows:
            p, name, t = row["player"], row["tutor"], row["cast_turn"]
            row["own_turn"] = (whose.get(t) == p) if t in whose else None
            row["held_turns"] = (t - row["drawn_turn"]) if (row.get("drawn_turn") is not None and t is not None) else None
            row["held_rounds"] = (rnd(t, seats) - rnd(max(1, row["drawn_turn"]), seats)) if row.get("drawn_turn") is not None and t else None
            # decider
            dec = "stock"
            for (tt, nm, want) in tcast.get(p, []):
                if tt == t and nm == name:
                    dec = "shim_tutor_cast"; row["seeking"] = want
            if row["agent"] != "plan":
                dec = "stock_seat"
            row["decider"] = dec
            # search_seen join: same player, src=name, turn >= t, first unused
            sj = None
            for k, s in enumerate(seen.get(p, [])):
                if (p, k) in used_seen:
                    continue
                if s.get("src") == name and s["turn"] is not None and t is not None and 0 <= s["turn"] - t <= 1:
                    sj = s; used_seen.add((p, k)); break
            taken = None
            if sj:
                row["search"] = {k: sj.get(k) for k in ("options", "sighted", "missing", "picked", "planPick", "dest", "comboPick", "pickedW", "planW", "sid")}
                st = steers.get((p, int(sj["sid"]))) if sj.get("sid") else None
                row["steer"] = st
                taken = st["steer"] if st else sj.get("picked")
            elif zi is not None:
                # stock inference: Library->X by this player between cast and the tutor's own Stack exit
                j = None
                for k in range(zi + 1, min(len(Z), zi + 400)):
                    if Z[k]["cardId"] == cid and Z[k]["from"] == "Stack":
                        j = k; break
                if j is not None:
                    cands = [Z[k] for k in range(zi + 1, j) if Z[k]["from"] == "Library"
                             and Z[k]["fromPlayer"] == p and Z[k].get("phase", "") != "DRAW"
                             and Z[k]["to"] != "Library"]
                    if name in TOP_TUTORS or not cands:
                        # top-of-library: Library->Library move of the fetched card inside the window, else next draw
                        ll = [Z[k] for k in range(zi + 1, j) if Z[k]["from"] == "Library" and Z[k]["to"] == "Library" and Z[k]["fromPlayer"] == p]
                        if ll:
                            taken = ll[-1]["card"]; row["taken_inferred"] = "lib->lib"
                        elif name in TOP_TUTORS:
                            for k in range(j + 1, len(Z)):
                                if Z[k]["from"] == "Library" and Z[k]["fromPlayer"] == p and Z[k]["to"] == "Hand":
                                    taken = Z[k]["card"]; row["taken_inferred"] = "next-draw"; break
                    if cands and taken is None:
                        taken = cands[0]["card"]; row["taken_inferred"] = "window"
                    row["resolved"] = Z[j]["to"]
                if taken is None and row["tutor"] in TUTORS:
                    row["taken_inferred"] = row.get("taken_inferred", "none")
            row["taken"] = taken
            # fate of taken card
            if taken:
                deck = row["deck"]
                plan = plans.get(deck, {}) if plans else {}
                lines = [set(l["cards"]) for l in plan.get("lines", [])]
                row["taken_is_line_piece"] = any(taken in l for l in lines)
                row["taken_target_value"] = plan.get("search", {}).get("targets", {}).get(taken)
                later = [f for f in fates.get((p, taken), []) if f[1] is not None and t is not None and f[1] >= t]
                cast = [f for f in later if f[3] in ("Stack", "Battlefield") and f[2] in ("Hand", "Library", "Exile", "Graveyard", "Command")]
                row["taken_used_turn"] = cast[0][1] if cast else None
                row["taken_used_delay_rounds"] = (rnd(cast[0][1], seats) - rnd(t, seats)) if cast else None
            out.append(row)
        yield from out

def main():
    arm = sys.argv[1]
    plans_arg = sys.argv[2]
    files = []
    for g in sys.argv[3:]:
        files += sorted(glob.glob(g))
    allrows = []
    for fn in files:
        pa = plans_arg
        if pa == "auto":
            # pick plans json in same dir matching pod id
            d = Path(fn).parent
            pod = re.search(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)", Path(fn).name)
            cand = []
            if pod:
                cand = list(d.glob(f"plans_{pod.group(1)}.json")) + list((d / "plans").glob(f"plans_{pod.group(1)}.json")) + list(d.parent.glob(f"plans_{pod.group(1)}.json"))
            if not cand:
                cand = sorted(d.glob("plans_*.json"))
            pa = str(cand[0]) if cand else "none"
        plans = load_plans(pa)
        for row in parse_file(fn, plans):
            row["plans_file"] = Path(pa).name if pa != "none" else None
            allrows.append(row)
    json.dump(allrows, open(HERE / f"rows_{arm}.json", "w"), indent=0)
    print(arm, len(files), "files", len(allrows), "tutor uses")

if __name__ == "__main__":
    main()
