"""Tutor extraction v2 (exact where the log is exact).

casts:    every tutor card that reached a seat's hand: when it arrived, whether
          and when it was cast from Hand/Command (zone stream, exact), phase,
          whose turn, decider (shim tutor_cast event vs stock).
searches: every non-land library search that resolved (STACK_RESOLVE text),
          with source, controller, turn/round; joined to the plan seat's
          search_seen/tutor_steer when present (exact pick), else inferred
          from the zone stream (Library->X by the controller in that turn).
Usage: py parse2.py <arm> <plans.json|auto|none> <glob>...
"""
import json, re, sys, glob, collections
from pathlib import Path

HERE = Path(__file__).parent
census = json.load(open(HERE / "census.json"))
TUTORS = {n for res in census.values() for n, c in res.items() if c["broad"]}
TUTOR_MODE = {}
for res in census.values():
    for n, c in res.items():
        TUTOR_MODE[n] = c["mode"]
LAND_CLAUSE = re.compile(r"\bland|plains|island|swamp|mountain|forest|gate\b", re.I)
SEARCH_TXT = re.compile(r"search(?:es)? (?:your|their) library(?: and/or graveyard)? for ([^,.]*)", re.I)
POD_RE = re.compile(r"(2iA_Jt0d6sM|n7WpsqsZtdQ|5A6o18Bra0Y|B421mac67IE|Bq-nFi0f1jA|CxKMqO36DdM|OuY6mdiXbHU|sZA0KqXCGrY)")

def rnd(turn, seats):
    return 0 if not turn or turn < 1 else (turn - 1) // seats + 1

def deck_of(p):
    return re.sub(r"^Ai\(\d+\)-", "", p or "")

def load_plans(path):
    if not path or path == "none":
        return {}
    p = json.load(open(path, encoding="utf-8"))
    return p.get("decks", p)

def parse_seen(detail):
    head, _, tail = detail.partition(" missing=")
    kv = dict(re.findall(r"(\w+)=([^ ]+)", head))
    m = re.match(r"(.*?) picked=(.*?) planPick=(.*?) src=(.*)$", tail)
    if m:
        kv["missing"], kv["picked"], kv["planPick"], kv["src"] = m.groups()
    return kv

def parse_file(fn, plans):
    games = collections.defaultdict(lambda: {"entries": [], "zones": [], "agent": [], "result": None})
    meta = None
    for line in open(fn, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        rec = r.get("rec")
        if rec == "meta":
            meta = r; continue
        g = r.get("game")
        if rec in ("entry", "zone", "agent"):
            games[g][{"entry": "entries", "zone": "zones", "agent": "agent"}[rec]].append(r)
        elif rec == "result":
            games[g]["result"] = r
    if not meta:
        return [], [], []
    players = meta["players"]
    seats = len(players)
    agents = dict(zip(players, meta.get("agents", ["?"] * seats)))
    casts, searches, gamesout = [], [], []
    for gi, G in sorted(games.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        res = G["result"]
        if res is None:
            continue
        winner = res.get("winner")
        gamesout.append({"file": Path(fn).name, "game": gi, "winner": winner, "turns": res.get("turns"),
                         "timedOut": res.get("timedOut"), "agents": agents, "seats": seats,
                         "shim": meta.get("shim"), "win_round": rnd(res.get("turns"), seats) if winner else None})
        whose = {}
        # entries -> search resolutions with turn
        turn = 0
        last_add = {}   # cardId -> player from STACK_ADD
        ent_searches = []
        for e in G["entries"]:
            t = e["type"]
            if t == "TURN":
                m = re.match(r"Turn (\d+) \((.+)\)", e["message"])
                if m:
                    turn = int(m.group(1)); whose[turn] = m.group(2)
            elif t == "STACK_ADD":
                m = re.match(r"(Ai\(\d+\)-\S+) (cast|activated|triggered) ", e["message"])
                if m and e.get("cardId") is not None:
                    last_add[e["cardId"]] = m.group(1)
            elif t == "STACK_RESOLVE":
                msg = e["message"]
                # the resolving object's own text is before any '[' annotation
                core = msg.split(" [")[0]
                sm = SEARCH_TXT.search(core)
                if not sm:
                    continue
                if LAND_CLAUSE.search(sm.group(1)):
                    continue
                pm = re.search(r"(Ai\(\d+\)-\S+) searches", core)
                ctl = pm.group(1) if pm else last_add.get(e.get("cardId"))
                ent_searches.append({"turn": turn, "src": e.get("card"), "ctl": ctl,
                                     "clause": sm.group(1)[:60]})
        # agent events
        ab = collections.defaultdict(list)
        for a in G["agent"]:
            ab[(a["player"], a["event"])].append(a)
        seen = {p: [dict(parse_seen(a["detail"]), turn=a["turn"]) for a in ab.get((p, "search_seen"), [])] for p in players}
        steer = {}
        for p in players:
            for a in ab.get((p, "tutor_steer"), []):
                m = re.match(r"sid=(\d+) mode=(\w+) value=(-?\d+) stockValue=(-?\d+) steer=(.*) over=(.*)$", a["detail"])
                if m:
                    steer[(p, m.group(1))] = {"mode": m.group(2), "value": int(m.group(3)), "stockValue": int(m.group(4)),
                                              "steer": m.group(5), "over": m.group(6)}
        tcast = collections.defaultdict(list)
        for p in players:
            for a in ab.get((p, "tutor_cast"), []):
                m = re.match(r"(.*) seeking (.*)$", a["detail"])
                if m:
                    tcast[p].append([a["turn"], m.group(1), m.group(2), False])
        Z = G["zones"]
        # ---- casts: per tutor cardId
        arrive, owner_of = {}, {}
        for i, z in enumerate(Z):
            if z["card"] in TUTORS and z["to"] == "Hand" and z["cardId"] not in arrive:
                arrive[z["cardId"]] = (z.get("turn"), z["toPlayer"], z["from"], z["card"])
        for i, z in enumerate(Z):
            if z["card"] in TUTORS and z["from"] in ("Hand", "Command") and z["to"] == "Stack":
                p = z["fromPlayer"]
                t = z.get("turn")
                dec = "stock"
                seek = None
                for tc in tcast.get(p, []):
                    if tc[0] == t and tc[1] == z["card"] and not tc[3]:
                        dec, seek, tc[3] = "shim", tc[2], True
                        break
                a = arrive.get(z["cardId"])
                casts.append({"file": Path(fn).name, "game": gi, "player": p, "deck": deck_of(p),
                              "agent": agents.get(p), "tutor": z["card"], "mode": TUTOR_MODE.get(z["card"]),
                              "from": z["from"], "drawn_turn": a[0] if a and a[1] == p else None,
                              "drawn_round": rnd(a[0], seats) if a and a[1] == p else None,
                              "cast_turn": t, "cast_round": rnd(t, seats), "phase": z.get("phase", ""),
                              "own_turn": whose.get(t) == p if t in whose else None,
                              "decider": dec, "seeking": seek, "winner": winner == p,
                              "win_round": rnd(res.get("turns"), seats) if winner == p else None,
                              "cid": z["cardId"]})
        cast_ids = {(c["cid"]) for c in casts if c["file"] == Path(fn).name and c["game"] == gi}
        # stranded: tutors that arrived in hand and were never cast from hand
        for cid, (t, p, frm, name) in arrive.items():
            if cid in cast_ids:
                continue
            # where did it end?
            last = [z for z in Z if z["cardId"] == cid][-1]
            casts.append({"file": Path(fn).name, "game": gi, "player": p, "deck": deck_of(p),
                          "agent": agents.get(p), "tutor": name, "mode": TUTOR_MODE.get(name),
                          "from": None, "drawn_turn": t, "drawn_round": rnd(t, seats), "cast_turn": None,
                          "cast_round": None, "phase": None, "own_turn": None, "decider": None,
                          "seeking": None, "winner": winner == p, "end_zone": last["to"],
                          "game_turns": res.get("turns"), "cid": cid})
        # unmatched tutor_cast events (shim chose a tutor but zone shows no cast that turn)
        for p in players:
            for tc in tcast.get(p, []):
                if not tc[3]:
                    casts.append({"file": Path(fn).name, "game": gi, "player": p, "deck": deck_of(p), "agent": agents.get(p),
                                  "tutor": tc[1], "decider": "shim_unmatched", "cast_turn": tc[0], "seeking": tc[2],
                                  "mode": TUTOR_MODE.get(tc[1])})
        # ---- searches
        used = set()
        used_zone = set()
        for s in ent_searches:
            p = s["ctl"]
            row = {"file": Path(fn).name, "game": gi, "player": p, "deck": deck_of(p), "agent": agents.get(p),
                   "src": s["src"], "clause": s["clause"], "turn": s["turn"], "round": rnd(s["turn"], seats),
                   "own_turn": whose.get(s["turn"]) == p, "winner": winner == p, "shim": meta.get("shim"),
                   "win_round": rnd(res.get("turns"), seats) if winner == p else None}
            plan = plans.get(deck_of(p), {}) if plans else {}
            lines = [l for l in plan.get("lines", [])]
            # plan-seat join
            if p in seen:
                for k, sv in enumerate(seen[p]):
                    if (p, k) in used:
                        continue
                    if sv.get("src") == s["src"] and sv["turn"] == s["turn"]:
                        used.add((p, k))
                        row["seen"] = {x: sv.get(x) for x in ("sid", "options", "sighted", "missing", "picked", "planPick", "dest", "comboPick", "pickedW", "planW", "ranked")}
                        st = steer.get((p, sv.get("sid")))
                        row["steer"] = st
                        row["taken"] = st["steer"] if st else sv.get("picked")
                        row["taken_how"] = "log"
                        break
            if "taken" not in row:
                # zone inference: first unused Library->non-Library move by p in that turn, not DRAW phase
                for i, z in enumerate(Z):
                    if i in used_zone:
                        continue
                    ty = z.get("types") or ""
                    if "Land" in ty and "Creature" not in ty and re.search(r"creature|artifact|instant|sorcery|enchantment|equipment|dragon", s["clause"], re.I):
                        continue
                    if z.get("turn") == s["turn"] and z["from"] == "Library" and z["fromPlayer"] == p \
                            and z["to"] in ("Hand", "Battlefield", "Graveyard", "Exile", "Library") \
                            and z.get("phase", "") != "DRAW":
                        used_zone.add(i)
                        row["taken"] = z["card"]; row["taken_how"] = "zone"; row["taken_to"] = z["to"]
                        break
            tk = row.get("taken")
            if tk and tk != "-":
                row["taken_line_piece"] = any(tk in l["cards"] for l in lines)
                row["taken_win_line_piece"] = any(tk in l["cards"] and is_win_line(l) for l in lines)
                row["taken_target"] = plan.get("search", {}).get("targets", {}).get(tk)
                later = [z for z in Z if z["card"] == tk and (z.get("toPlayer") == p or z.get("fromPlayer") == p)
                         and (z.get("turn") or 0) >= s["turn"] and z["to"] in ("Stack", "Battlefield")]
                row["taken_used_turn"] = later[0].get("turn") if later else None
            searches.append(row)
    return casts, searches, gamesout

WIN_PAT = re.compile(r"win the game|infinite damage|infinite lifeloss|infinite life loss|lose the game|"
                     r"near-infinite damage|infinite mill|near-infinite mill|infinite combat|"
                     r"infinitely large creature|infinite power|infinitely powerful|infinite death triggers|"
                     r"infinite storm", re.I)

def is_win_line(line):
    prods = " ".join(line.get("produces", []))
    return bool(WIN_PAT.search(prods))

def main():
    arm, plans_arg = sys.argv[1], sys.argv[2]
    files = []
    for g in sys.argv[3:]:
        files += sorted(glob.glob(g))
    C, S, Gs = [], [], []
    for fn in files:
        pa = plans_arg
        if pa == "auto":
            d = Path(fn).parent
            m = POD_RE.search(Path(fn).name)
            cand = []
            if m:
                for base in (d, d / "plans", d.parent):
                    cand += list(base.glob(f"plans_{m.group(1)}.json"))
            pa = str(cand[0]) if cand else "none"
        c, s, g = parse_file(fn, load_plans(pa))
        C += c; S += s; Gs += g
    json.dump({"casts": C, "searches": S, "games": Gs}, open(HERE / f"v2_{arm}.json", "w"))
    print(f"{arm}: files={len(files)} games={len(Gs)} tutor-cards={len(C)} searches={len(S)}")

if __name__ == "__main__":
    main()
