#!/usr/bin/env python3
"""MTG Rules Engine — backend brains for any front end.

Wraps the rules KB (../rules/kb) and the Forge simulation pipeline behind one
zero-dependency API. Use it three ways:

  1. Python import:      from mtg_engine import Engine; e = Engine(); e.rule("903.10a")
  2. CLI:                python3 mtg_engine.py rule 903.10a
                         python3 mtg_engine.py search "commander damage"
                         python3 mtg_engine.py keyword station
                         python3 mtg_engine.py turn-structure
  3. HTTP (front ends):  python3 mtg_engine.py serve 8484
       GET  /rule/903.10a         exact rule + subrules
       GET  /search?q=trample     scored free-text search
       GET  /keyword/foretell     keyword ability/action entry
       GET  /glossary/monarch     glossary term
       GET  /turn-structure       ordered phases/steps with rules attached
       GET  /health               KB stats
       GET  /results              index of adapted sim result files
       GET  /results/{file}       one full sim result (games -> turns -> events)
                                  ?snapshots=1 adds board_snapshot events
       GET  /cards?names=a|b|c    Scryfall card facts (cached); ?fetch=0 for cache-only
       GET  /board/{file}         board-reconstruction accuracy report
       GET  /analysis/{file}      wincon report: win methods, combo assembly/conversion
       POST /simulate             {"decks":[...], "games":N, "deck_dir":"..."} -> sim JSON
       POST /decks                {"name":..., "text":..., "commander"?} -> validated .dck
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "rules" / "kb"


class Engine:
    def __init__(self, kb_dir: Path | str = KB):
        self.kb = Path(kb_dir)
        self._rules = json.loads((self.kb / "all_rules.json").read_text(encoding="utf-8"))
        self._glossary = json.loads((self.kb / "glossary.json").read_text(encoding="utf-8"))
        mech = json.loads((self.kb / "mechanics.json").read_text(encoding="utf-8"))
        self._keywords = {e["name"].lower(): e for e in mech["keyword_abilities"]}
        self._keywords.update({e["name"].lower(): e for e in mech["keyword_actions"]})
        self._turns = json.loads((self.kb / "turn_structure.json").read_text(encoding="utf-8"))
        self._chunks = None  # lazy — 3,887 lines

    # ---------- lookups ----------

    def rule(self, number: str) -> dict:
        """Exact rule + its direct subrules (903.10 also returns 903.10a...)."""
        number = number.rstrip(".")
        hits = {k: v for k, v in self._rules.items()
                if k == number or re.fullmatch(re.escape(number) + r"[a-z]", k)}
        if not hits:
            return {"error": f"rule {number} not found", "suggestion": self._nearest_rule(number)}
        return {"rule": number, "entries": [
            {"rule": k, "text": v["text"] if isinstance(v, dict) else str(v)} for k, v in sorted(hits.items())
        ]}

    def keyword(self, name: str) -> dict:
        e = self._keywords.get(name.lower().strip())
        return e if e else {"error": f"keyword '{name}' not found",
                            "close": [k for k in self._keywords if name.lower()[:4] in k][:5]}

    def glossary(self, term: str) -> dict:
        for k, v in self._glossary.items():
            if k.lower() == term.lower().strip():
                return {"term": k, **v}
        close = [k for k in self._glossary if term.lower() in k.lower()][:8]
        return {"error": f"term '{term}' not found", "close": close}

    def turn_structure(self) -> dict:
        return self._turns

    def search(self, query: str, k: int = 8) -> list[dict]:
        """Keyword-overlap scored search over the retrieval chunks."""
        if self._chunks is None:
            self._chunks = [json.loads(line) for line in
                            (self.kb / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        words = [w for w in re.findall(r"[a-z0-9']+", query.lower()) if len(w) > 2]
        if not words:
            return []
        scored = []
        for c in self._chunks:
            t = c["text"].lower()
            score = sum(t.count(w) for w in words)
            exact = 3 if query.lower() in t else 0
            if score:
                scored.append((score + exact, c))
        scored.sort(key=lambda x: -x[0])
        return [{"score": s, "id": c["id"], "rule": c.get("rule") or c.get("term"),
                 "text": c["text"][:400]} for s, c in scored[:k]]

    def validate_game_log(self, path: str) -> dict:
        """Check every rule_ref in a training game_log resolves in the KB."""
        log = json.loads(Path(path).read_text(encoding="utf-8"))
        refs, missing = set(), []
        def walk(o):
            if isinstance(o, dict):
                rr = o.get("rule_refs")
                if isinstance(rr, list):  # skip descriptive strings (e.g. schema notes)
                    for r in rr:
                        tok = re.split(r"\s", str(r))[0].strip("?.,;()")
                        if re.match(r"^\d{3}(\.\d+[a-z]?)?$", tok):
                            refs.add(tok)
                        else:
                            refs.add(str(r))  # keep non-numeric refs visible in report
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(log)
        for r in sorted(refs):
            base = r.rstrip(".")
            if base not in self._rules and not any(k.startswith(base) for k in self._rules):
                missing.append(r)
        return {"file": path, "refs_checked": len(refs), "missing": missing, "ok": not missing}

    # ---------- simulation ----------

    def simulate(self, decks: list[str], games: int = 10, deck_dir: str | None = None,
                 fmt: str = "Commander", forge_jar: str | None = None, out: str = "./sim_results",
                 run_id: str | None = None) -> dict:
        import subprocess
        cmd = [sys.executable, str(Path(__file__).parent / "run_sim.py"),
               "--decks", *decks, "--games", str(games), "--format", fmt, "--out", out]
        if run_id:
            cmd += ["--run-id", run_id]
        if deck_dir:
            cmd += ["--deck-dir", deck_dir]
        if forge_jar:
            cmd += ["--forge-jar", forge_jar]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        latest = sorted(Path(out).glob("sim_*.json"))
        return {"stdout": (proc.stdout + "\n" + proc.stderr)[-2000:], "returncode": proc.returncode,
                "result_file": str(latest[-1]) if latest else None,
                "result": json.loads(latest[-1].read_text()) if latest and proc.returncode == 0 else None}

    # ---------- helpers ----------

    def _nearest_rule(self, number: str) -> list[str]:
        prefix = number.split(".")[0]
        return [k for k in self._rules if k.startswith(prefix + ".")][:6]

    def stats(self) -> dict:
        return {"rules": len(self._rules), "keywords": len(self._keywords),
                "glossary_terms": len(self._glossary), "kb_dir": str(self.kb)}


# ---------- HTTP server (stdlib only) ----------

BUNDLED_DECKS = Path(__file__).parent / "decks"
# Imported decks go on the shared data volume, NOT into the API's image. The
# worker is a separate container: a deck written inside the API image passes the
# allowlist, enqueues, and then the worker cannot find the file. Both processes
# mount MTG_DATA_DIR, so that is the only place an imported deck is reachable.
IMPORTED_DECKS = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent))) / "decks"


def _deck_dirs() -> list[Path]:
    """Where decks live, in lookup order: imported (shared volume) then bundled."""
    return [IMPORTED_DECKS, BUNDLED_DECKS]


def _find_deck(filename: str) -> Path | None:
    """Resolve a deck filename to a real path, refusing traversal."""
    if filename != Path(filename).name or not filename.endswith(".dck"):
        return None
    for d in _deck_dirs():
        p = d / filename
        if p.is_file():
            return p
    return None


def _list_decks() -> list[dict]:
    decks: dict[str, dict] = {}
    for d in _deck_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.dck")):
            if f.name in decks:
                continue          # first match wins: imported shadows bundled
            name = f.stem
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if line.startswith("Name="):
                        name = line[5:].strip()
                        break
            except OSError:
                continue
            decks[f.name] = {"file": f.name, "name": name,
                             "source": "imported" if d == IMPORTED_DECKS else "bundled"}
    return [decks[k] for k in sorted(decks)]


def _queued_count() -> int:
    """How many jobs are waiting or running — the backpressure signal."""
    try:
        import jobqueue
        import sqlite3
        with sqlite3.connect(jobqueue.DB_PATH, timeout=5) as c:
            row = c.execute(
                "SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0   # never let a bookkeeping failure block a legitimate request


def _job_status(job_id: str | None) -> dict:
    """Dashboard-friendly view of a queue job (latest job when id is None)."""
    import jobqueue
    job = jobqueue.get(job_id)
    if not job:
        return {"state": "idle"}
    out = {"state": job["state"], "id": job["id"], "decks": job["decks"],
           "games": job["games"], "started": job["started"],
           "elapsed": job.get("elapsed"), "error": job["error"]}
    if job["state"] == "queued":
        # Report the truth. Calling a queued job "running" meant that behind a
        # backlog you watched an elapsed timer tick for a job Forge had not
        # started, with no way to tell the difference.
        out["queued_ahead"] = jobqueue.position(job["id"])
    if job.get("result"):
        out["result"] = job["result"].get("summary")
        out["result_file"] = job["result"].get("result_file")
    return out


RESULTS_DIR = Path(os.environ.get("MTG_DATA_DIR", str(Path(__file__).parent))) / "sim_results"

# ---------- deployment configuration (all env-driven; safe local defaults) ----------

# Comma-separated API keys permitted to POST /simulate and /decks. When empty the
# server is OPEN — fine for localhost, never for a public deployment, so serve()
# refuses to bind a non-loopback interface without keys unless explicitly allowed.
API_KEYS = {k.strip() for k in os.environ.get("MTG_API_KEYS", "").split(",") if k.strip()}
ALLOW_ORIGIN = os.environ.get("MTG_ALLOW_ORIGIN", "*")
GZIP_MIN = int(os.environ.get("MTG_GZIP_MIN_BYTES", "1024"))
# Simulations are the expensive resource: a 4GB JVM for 10-60 minutes.
SIM_PER_HOUR = int(os.environ.get("MTG_SIM_PER_HOUR", "6"))
SIM_MAX_GAMES = int(os.environ.get("MTG_SIM_MAX_GAMES", "64"))
SIM_MAX_QUEUED = int(os.environ.get("MTG_SIM_MAX_QUEUED", "3"))
READ_PER_MIN = int(os.environ.get("MTG_READ_PER_MIN", "240"))
ALLOW_OPEN_PUBLIC = os.environ.get("MTG_ALLOW_OPEN_PUBLIC", "0") == "1"

_rate_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def _bearer(header: str) -> str:
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def _rate_ok(bucket: str, limit: int, window: float) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, retry_after_seconds).

    In-process by design: one API container is the documented topology. Running
    several replicas needs a shared store (see deploy_plan.md).
    """
    now = time.time()
    with _rate_lock:
        hits = [t for t in _hits.get(bucket, []) if now - t < window]
        if len(hits) >= limit:
            _hits[bucket] = hits
            return False, max(1, int(window - (now - hits[0])))
        hits.append(now)
        _hits[bucket] = hits
        return True, 0


def _list_results() -> list[dict]:
    """Index of adapted sim result files, newest first."""
    out = []
    for f in sorted(RESULTS_DIR.glob("sim_*.json"), reverse=True):
        entry = {"file": f.name, "bytes": f.stat().st_size,
                 "modified": int(f.stat().st_mtime)}
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            entry["decks"] = d.get("meta", {}).get("decks", [])
            entry["games"] = len(d.get("games", []))
            entry["summary"] = d.get("summary")
        except Exception as e:  # noqa: BLE001 — surface bad files in the index
            entry["error"] = f"unreadable: {e}"
        out.append(entry)
    return out


def _read_result(name: str, snapshots: bool = False) -> dict:
    """One full sim result JSON by bare filename (no path traversal).

    With snapshots=True, board.py adds an end-of-turn board_snapshot event to each
    turn. That reconstruction is inference (Forge logs no battlefield entries), so
    meta.board_snapshots records how it was derived.
    """
    if name != Path(name).name or not name.endswith(".json"):
        raise ValueError("bad result filename")
    f = RESULTS_DIR / name
    if not f.is_file():
        raise FileNotFoundError(name)
    data = json.loads(f.read_text(encoding="utf-8"))
    if snapshots and "board_snapshots" not in data.get("meta", {}):
        import board
        data = board.annotate(data, fetch=False)  # cache-only: never blocks a request
    return data


def _read_result_summary(name: str) -> dict:
    """A run without its event logs — what the results page actually needs.

    A full run file averages 2.6 MB and reaches 5.7 MB; the summary is a few KB,
    so the results table no longer costs a multi-megabyte download.
    """
    data = _read_result(name)
    games = []
    for i, g in enumerate(data.get("games", []), 1):
        turns = g.get("turns", [])
        games.append({
            "n": i,
            "players": g.get("players", []),
            "result": g.get("result"),
            "turns": len(turns),
            "ended_turn": turns[-1].get("turn") if turns else None,
            "events": sum(len(t.get("events", [])) for t in turns),
        })
    return {"meta": data.get("meta", {}), "summary": data.get("summary"),
            "games": games, "file": name}


def _read_result_game(name: str, n: int, snapshots: bool = False) -> dict:
    """One game out of a run — the payload a replay actually needs."""
    data = _read_result(name, snapshots=snapshots)
    games = data.get("games", [])
    if n < 1 or n > len(games):
        raise IndexError(f"game {n} not in {name} (has {len(games)})")
    return {"meta": data.get("meta", {}), "file": name, "n": n,
            "games_total": len(games), "game": games[n - 1]}


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _read_live(job_id: str, n: int | None = None) -> dict:
    """GET /sim-live — the game currently being played, from the partial log.

    Forge's stdout is already streamed to forge_raw_<job_id>.log line by line
    while the match runs, and parse_forge_log() is a pure function over whatever
    text it is handed. So "watching live" is just parsing the prefix that exists
    so far: the trailing game has no `Game Result` line yet and comes back with
    the turns played up to this instant.

    Shaped like /results/{file}/game/{n} so the front end can reuse the same
    timeline fold for a live game and a finished one.
    """
    if not _JOB_ID_RE.match(job_id or ""):
        raise ValueError("bad job id")            # keeps the id out of path building
    f = RESULTS_DIR / f"forge_raw_{job_id}.log"
    if not f.is_file():
        raise FileNotFoundError("no live log for this job yet")

    from forge_log_adapter import parse_forge_log
    text = f.read_text(encoding="utf-8", errors="replace")
    parsed = parse_forge_log(text, source="live")
    games = parsed.get("games") or []
    if not games:
        # Forge is still loading its card database; nothing has been played yet.
        return {"job_id": job_id, "games_done": 0, "n": 0, "game": None,
                "in_progress": True, "bytes": len(text)}

    # Clamp rather than 404. A viewer plays games back in order while Forge runs
    # ahead of it, so it asks for game N as a matter of course before N exists;
    # that is a normal race, not a bad request. games_seen tells it where it is.
    idx = len(games) if n is None else max(1, min(n, len(games)))
    game = dict(games[idx - 1])
    live = game.get("result") is None
    if live:
        # The client's types require a result object; say plainly it is unfinished
        # rather than inventing a winner.
        game["result"] = {"winner": None, "draw": False, "duration_ms": 0, "raw": ""}
    game["n"] = idx
    return {"job_id": job_id, "games_done": sum(1 for g in games if g.get("result")),
            "n": idx, "games_seen": len(games), "game": game,
            "in_progress": live, "bytes": len(text)}


def _read_analysis(name: str, fetch: bool = True) -> dict:
    """GET /analysis/{file} — wincon report for a finished run.

    Result files never change, so the report is computed once and cached beside
    them ("analysis_<file>"; _list_results globs sim_*.json, so no collision).
    First computation may make one Spellbook POST per previously-unseen deck;
    everything after that is disk reads.
    """
    result = _read_result(name)          # validates the name against traversal
    import analysis
    cache = RESULTS_DIR / f"analysis_{name}"
    src = RESULTS_DIR / name
    if cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        # The maths and payload evolve; a cached report from an older analysis
        # version silently serving the old shape is worse than recomputing.
        if cached.get("version") == analysis.ANALYSIS_VERSION:
            return cached
    result.setdefault("file", name)
    rep = analysis.analyse(result, fetch=fetch)
    try:
        cache.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass                              # read-only volume: serve uncached
    return rep


def _deck_combos(content: str) -> dict:
    """Combo block for an import response. Never fatal — the deck is already
    saved, and 'unknown' is an honest answer when Spellbook is unreachable."""
    try:
        import combos
        main, commanders = combos.parse_dck(content)
        found = combos.find_combos(main, commanders)
        if found is None:
            return {"status": "unknown"}
        # "One card away": which single add unlocks the most known combos. The
        # deck's own names, normalized, subtracted from each almost-combo's
        # card list leave exactly the missing piece.
        import cards
        def norm(n: str) -> str:
            return cards.normalize_name(n.split(" // ")[0]).lower()
        have = {norm(n) for n, _ in main} | {norm(n) for n in commanders}
        by_missing: dict = {}
        for c in found["almost_included"]:
            missing = [n for n in c["cards"] if norm(n) not in have]
            if len(missing) != 1:
                continue          # colour-identity or multi-card gaps: not a swap
            slot = by_missing.setdefault(missing[0], {
                "missing": missing[0], "unlocks": 0,
                "example": c["cards"], "produces": c["produces"][:3]})
            slot["unlocks"] += 1
        one_away = sorted(by_missing.values(), key=lambda x: -x["unlocks"])[:6]
        return {"status": "ok",
                "included": found["included"],
                "almost_included": len(found["almost_included"]),
                "one_away": one_away}
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"combo lookup skipped: {e}\n")
        return {"status": "unknown"}


def _cards_lookup(names: list[str], fetch: bool = True) -> dict:
    """Scryfall facts for the UI: type lines, P/T, mana cost, oracle text, art."""
    import cards
    found = cards.get_many(names, fetch=fetch)
    return {"cards": found,
            "missing": sorted({cards.normalize_name(n) for n in names
                               if cards.normalize_name(n) not in found
                               and not cards.is_token(n)}),
            "cache": cards.stats()}


def _import_deck(payload: dict) -> dict:
    """POST /decks — convert a pasted list via convert_decklist.convert().

    Tolerant by contract: hard parse failures come back as {"ok": false, "error"},
    never a 500; the caller's text is never modified (fixes are suggestions)."""
    from convert_decklist import convert
    text = payload.get("text", "")
    name = (payload.get("name") or "").strip() or "Imported Deck"
    commander = payload.get("commander") or None
    try:
        content, report = convert(text, name, commander)
    except SystemExit as e:  # convert() sys.exit()s on hard failures
        return {"ok": False, "error": str(e)}
    # Name-only slugs collide: two callers importing "Zombies" overwrite each
    # other. Suffix with a content hash so distinct lists get distinct files and
    # re-importing the same list is idempotent.
    import hashlib
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "deck"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    slug = f"{base}_{digest}.dck"
    saved = bool(payload.get("save", True))
    if saved:
        IMPORTED_DECKS.mkdir(parents=True, exist_ok=True)
        (IMPORTED_DECKS / slug).write_text(content, encoding="utf-8")
    return {"ok": True, "file": slug, "saved": saved, "report": report,
            "cards_cached": _warm_card_cache(content),
            "combos": _deck_combos(content)}


def _deck_card_names(dck: str) -> list[str]:
    """Card names out of a .dck body — the "N Name" lines under [Commander]/[Main]."""
    names, section = [], ""
    for line in dck.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.lower()
            continue
        if section not in ("[commander]", "[main]"):
            continue
        m = re.match(r"^\d+\s+(.+)$", line)
        if m:
            names.append(m.group(1).strip())
    return names


def _warm_card_cache(dck: str) -> int:
    """Pull every card in a freshly imported deck into the Scryfall cache.

    Import is the one moment we know the full card list before anyone needs it,
    so it is the cheapest place to pay for art and type lines: ~100 names is two
    batched /cards/collection calls, and it means the replay tabletop and the
    board's type grouping render from a warm cache instead of fetching mid-scrub.
    Never fatal — the deck is already written, and every consumer of card facts
    degrades to names only.
    """
    try:
        import cards
        return cards.fetch_missing(_deck_card_names(dck))
    except Exception as e:  # noqa: BLE001 — Scryfall down must not fail an import
        sys.stderr.write(f"card cache warm skipped: {e}\n")
        return 0


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>MTG Engine</title><style>
body{font-family:-apple-system,Segoe UI,sans-serif;background:#14171c;color:#e6e6e6;max-width:760px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.3rem} .card{background:#1d2129;border:1px solid #2c313c;border-radius:10px;padding:1rem;margin:1rem 0}
label.deck{display:block;padding:.35rem .5rem;border-radius:6px;cursor:pointer} label.deck:hover{background:#262b36}
button{background:#3b82f6;color:#fff;border:0;border-radius:8px;padding:.6rem 1.4rem;font-size:1rem;cursor:pointer}
button:disabled{background:#555} input[type=number]{width:5rem;background:#262b36;color:#fff;border:1px solid #3a404d;border-radius:6px;padding:.4rem}
table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #2c313c;padding:.45rem;text-align:left}
.bar{background:#3b82f6;height:10px;border-radius:5px} #status{color:#9aa4b2} .err{color:#f87171;white-space:pre-wrap}
</style></head><body>
<h1>&#9876;&#65039; MTG Engine &mdash; Deck Simulator</h1>
<div class="card"><b>Pick 2&ndash;4 decks</b><div id="decks">loading&hellip;</div></div>
<div class="card">Games: <input id="games" type="number" value="10" min="1" max="200">
&nbsp;<button id="run" onclick="runSim()">Run simulation</button> <span id="status"></span></div>
<div class="card" id="results" style="display:none"></div>
<div class="card"><b>Rules lookup</b><br><input id="q" style="width:70%" placeholder="e.g. 903.10a or 'commander damage'">
<button onclick="lookup()">Search</button><pre id="ruleout" style="white-space:pre-wrap"></pre></div>
<script>
async function load(){const d=await(await fetch('/decks')).json();
document.getElementById('decks').innerHTML=d.map(x=>`<label class="deck"><input type="checkbox" value="${x.file}"> ${x.name} <span style="color:#9aa4b2">(${x.file})</span></label>`).join('');}
async function runSim(){const decks=[...document.querySelectorAll('#decks input:checked')].map(c=>c.value);
if(decks.length<2||decks.length>4){alert('Pick 2-4 decks');return}
document.getElementById('run').disabled=true;
const rsp=await(await fetch('/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decks,games:+document.getElementById('games').value})})).json();
poll(rsp.job_id);}
async function poll(id){const s=await(await fetch('/sim-status'+(id?'?id='+id:''))).json();const st=document.getElementById('status');
if(s.state==='running'){st.textContent=`running ${s.games||''} game(s)… ${s.started?Math.round((Date.now()/1000)-s.started)+'s':'queued'}`;setTimeout(()=>poll(id),4000);}
else if(s.state==='done'){st.textContent=`done in ${s.elapsed}s`;document.getElementById('run').disabled=false;show(s);}
else if(s.state==='error'){st.innerHTML='<span class="err">'+(s.error||'failed')+'</span>';document.getElementById('run').disabled=false;}
else st.textContent='';}
function show(s){const r=s.result;const el=document.getElementById('results');el.style.display='block';
const rows=Object.entries(r.win_rates).sort((a,b)=>b[1]-a[1]).map(([p,w])=>
`<tr><td>${p.replace(/^Ai\\(\\d+\\)-/,'')}</td><td>${r.wins[p]}</td><td style="width:45%"><div class="bar" style="width:${w*100}%"></div></td><td>${(w*100).toFixed(0)}%</td></tr>`).join('');
el.innerHTML=`<b>${r.games} games, ${r.draws} draws</b><table><tr><th>Deck</th><th>Wins</th><th></th><th>Rate</th></tr>${rows}</table>
<small style="color:#9aa4b2">full event log: ${s.result_file||''}</small>`;}
async function lookup(){const q=document.getElementById('q').value.trim();if(!q)return;
const url=/^\\d{3}(\\.|$)/.test(q)?'/rule/'+encodeURIComponent(q):'/search?q='+encodeURIComponent(q);
document.getElementById('ruleout').textContent=JSON.stringify(await(await fetch(url)).json(),null,1);}
load();poll();
</script></body></html>"""


def serve(port: int = 8484) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs, unquote

    engine = Engine()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"   # keep-alive; requires accurate Content-Length

        # ---- request context ----
        @property
        def client_key(self) -> str:
            """Identity for rate limiting: credential when present, else client IP.

            Hashed in full, never truncated. A prefix would collapse callers into
            one bucket the moment credentials share a prefix — every RS256 JWT
            from the same issuer starts with the same base64 header, so
            `token[:12]` would give all authenticated users a single shared quota.
            """
            k = _bearer(self.headers.get("Authorization", "")) or self.headers.get("X-Api-Key", "")
            if k:
                import hashlib
                return "key:" + hashlib.sha256(k.encode()).hexdigest()[:16]
            return f"ip:{self.client_address[0]}"

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
            if ALLOW_ORIGIN != "*":
                self.send_header("Vary", "Origin")

        def _send(self, obj, code=200, cache: str | None = None):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            enc = None
            # Results and card payloads are large and highly compressible.
            if len(body) > GZIP_MIN and "gzip" in self.headers.get("Accept-Encoding", ""):
                import gzip as _gz
                body, enc = _gz.compress(body, 6), "gzip"
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if enc:
                self.send_header("Content-Encoding", enc)
            self._cors()
            if cache:
                self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # client navigated away mid-download; not an error worth logging

        def _send_html(self, html: str):
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # ---- gates ----
        def _authed(self) -> bool:
            """True when the caller may perform expensive/writing operations."""
            if not API_KEYS:
                return True   # open mode; serve() has already warned about this
            key = _bearer(self.headers.get("Authorization", "")) or \
                self.headers.get("X-Api-Key", "")
            return key in API_KEYS

        def _deny(self, code: int, msg: str, retry: int = 0):
            if retry:
                self.send_response(code)
                self.send_header("Retry-After", str(retry))
                self.send_header("Content-Type", "application/json")
                self._cors()
                body = json.dumps({"error": msg, "retry_after": retry}).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._send({"error": msg}, code)

        def do_GET(self):
            u = urlparse(self.path)
            parts = [unquote(p) for p in u.path.strip("/").split("/") if p]
            q = parse_qs(u.query)
            ok, retry = _rate_ok(f"read:{self.client_key}", READ_PER_MIN, 60.0)
            if not ok:
                return self._deny(429, "too many requests", retry)
            try:
                if not parts:
                    return self._send_html(DASHBOARD_HTML)
                if parts[0] == "health":
                    return self._send(engine.stats())
                if parts[0] == "decks":
                    return self._send(_list_decks())
                if parts[0] == "sim-status":
                    return self._send(_job_status(q.get("id", [None])[0]))
                if parts[0] == "sim-live":
                    raw_n = q.get("game", [None])[0]
                    try:
                        return self._send(_read_live(q.get("id", [""])[0],
                                                     int(raw_n) if raw_n else None))
                    except FileNotFoundError as e:
                        return self._send({"error": str(e)}, 404)
                    except (IndexError, ValueError) as e:
                        return self._send({"error": str(e)}, 400)
                if parts[0] == "rule" and len(parts) > 1:
                    return self._send(engine.rule(parts[1]))
                if parts[0] == "keyword" and len(parts) > 1:
                    return self._send(engine.keyword(parts[1]))
                if parts[0] == "glossary" and len(parts) > 1:
                    return self._send(engine.glossary(parts[1]))
                if parts[0] == "turn-structure":
                    return self._send(engine.turn_structure())
                if parts[0] == "search":
                    return self._send(engine.search(q.get("q", [""])[0], int(q.get("k", ["8"])[0])))
                if parts[0] == "results":
                    if len(parts) == 1:
                        return self._send(_list_results())
                    snaps = q.get("snapshots", ["0"])[0] not in ("0", "", "false")
                    IMMUTABLE = "public, max-age=31536000, immutable"  # results never change
                    try:
                        # /results/{file}/game/{n} — one game, not the whole run
                        if len(parts) >= 4 and parts[2] == "game":
                            return self._send(
                                _read_result_game(parts[1], int(parts[3]), snapshots=snaps),
                                cache=IMMUTABLE)
                        if len(parts) >= 3 and parts[2] == "summary":
                            return self._send(_read_result_summary(parts[1]), cache=IMMUTABLE)
                        return self._send(_read_result(parts[1], snapshots=snaps),
                                          cache=IMMUTABLE)
                    except FileNotFoundError:
                        return self._send({"error": "no such result"}, 404)
                    except (IndexError, ValueError) as e:
                        return self._send({"error": str(e)}, 404)
                if parts[0] == "cards":
                    raw = q.get("names", [""])[0]
                    names = [n for n in re.split(r"[|\n]", raw) if n.strip()]
                    if not names:
                        return self._send({"error": "pass ?names=a|b|c"}, 400)
                    fetch = q.get("fetch", ["1"])[0] not in ("0", "", "false")
                    return self._send(_cards_lookup(names, fetch=fetch))
                if parts[0] == "analysis" and len(parts) > 1:
                    fetch = q.get("fetch", ["1"])[0] not in ("0", "", "false")
                    try:
                        # No immutable header: the report is versioned and can be
                        # recomputed with new maths for the same result file. A
                        # client that pinned v1 forever kept rendering it after
                        # the engine moved to v2. Computation is disk-cached
                        # server-side, so serving it fresh is cheap.
                        return self._send(_read_analysis(parts[1], fetch=fetch))
                    except (FileNotFoundError, ValueError):
                        # ValueError is the traversal guard — same 404 as /results.
                        return self._send({"error": "no such result"}, 404)
                if parts[0] == "board" and len(parts) > 1:
                    import board
                    try:
                        return self._send(board.validate(_read_result(parts[1]), fetch=False))
                    except FileNotFoundError:
                        return self._send({"error": "no such result"}, 404)
                return self._send({"error": "unknown endpoint"}, 404)
            except Exception as e:  # noqa: BLE001
                return self._send({"error": str(e)}, 500)

        def do_POST(self):
            u = urlparse(self.path)
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            try:
                route = u.path.strip("/")
                if route in ("simulate", "decks") and not self._authed():
                    return self._deny(401, "an API key is required for this endpoint")

                if route == "simulate":
                    import jobqueue
                    decks = payload.get("decks") or []
                    games = int(payload.get("games") or 0)
                    # Validate before spending anything: each job is a 4GB JVM for
                    # 10-60 minutes, so the cheap checks come first.
                    if not 2 <= len(decks) <= 4:
                        return self._send({"error": "pick 2 to 4 decks"}, 400)
                    unknown = [d for d in decks if _find_deck(d) is None]
                    if unknown:
                        return self._send({"error": f"unknown decks: {unknown}"}, 400)
                    if not 1 <= games <= SIM_MAX_GAMES:
                        return self._send(
                            {"error": f"games must be 1..{SIM_MAX_GAMES}"}, 400)
                    queued = _queued_count()
                    if queued >= SIM_MAX_QUEUED:
                        return self._deny(
                            503, f"{queued} simulations already queued; try later", 120)
                    ok, retry = _rate_ok(f"sim:{self.client_key}", SIM_PER_HOUR, 3600.0)
                    if not ok:
                        return self._deny(
                            429, f"simulation quota is {SIM_PER_HOUR}/hour", retry)
                    # Tell the worker where each deck actually lives. Imported
                    # decks are on the shared volume, not in the worker's image.
                    resolved = {d: _find_deck(d) for d in decks}
                    dirs = {str(p.parent) for p in resolved.values() if p}
                    job: dict = {"decks": decks, "games": games}
                    if len(dirs) == 1:
                        job["deck_dir"] = dirs.pop()
                    else:
                        # Mixed bundled/imported: pass absolute paths instead.
                        job["decks"] = [str(resolved[d]) for d in decks]
                    job_id = jobqueue.enqueue(job)
                    return self._send({"ok": True, "job_id": job_id, "state": "queued"})

                if route == "decks":
                    ok, retry = _rate_ok(f"imp:{self.client_key}", 30, 3600.0)
                    if not ok:
                        return self._deny(429, "deck-import quota is 30/hour", retry)
                    if len(payload.get("text", "")) > 100_000:
                        return self._send({"error": "decklist too large"}, 413)
                    return self._send(_import_deck(payload))
                return self._send({"error": "unknown endpoint"}, 404)
            except Exception as e:  # noqa: BLE001
                return self._send({"error": str(e)}, 500)

        def do_OPTIONS(self):  # CORS preflight for cross-origin front ends
            self.send_response(204)
            # Same origin policy as the real responses. Hardcoding "*" here let a
            # deployment that set MTG_ALLOW_ORIGIN preflight from any origin.
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            # Authorization and X-Api-Key must be listed or the browser drops the
            # header before the request is sent: _authed() would then see no
            # credential and 401 every keyed POST from the front end.
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, Authorization, X-Api-Key")
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()

        def log_message(self, fmt, *args):  # quieter default
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # Check the bind posture BEFORE starting a worker, so a refusal costs nothing.
    # Binding a public interface with no API keys turns POST /simulate into a free
    # compute faucet (a 4GB JVM per request). Refuse by default; MTG_ALLOW_OPEN_PUBLIC=1
    # is the deliberate override for a trusted private network.
    host = os.environ.get("MTG_BIND", "0.0.0.0")
    public = host not in ("127.0.0.1", "localhost", "::1")
    if public and not API_KEYS and not ALLOW_OPEN_PUBLIC:
        sys.exit(
            f"refusing to bind {host}:{port} with no API keys.\n"
            "  set MTG_API_KEYS=key1,key2  (recommended), or\n"
            "  set MTG_BIND=127.0.0.1 for local-only, or\n"
            "  set MTG_ALLOW_OPEN_PUBLIC=1 to override on a trusted network."
        )
    import worker
    worker.ensure_embedded()  # no-op when MTG_EMBEDDED_WORKER=0 (deployed mode)

    mode = f"{len(API_KEYS)} API key(s)" if API_KEYS else "OPEN — no auth"
    print(f"MTG engine API on http://{host}:{port}  [{mode}]")
    print(f"  limits: {SIM_PER_HOUR} sims/hour/caller, <={SIM_MAX_GAMES} games, "
          f"{SIM_MAX_QUEUED} queued max, {READ_PER_MIN} reads/min")
    if not API_KEYS:
        print("  WARNING: /simulate and /decks are unauthenticated", file=sys.stderr)

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True   # don't let in-flight requests block shutdown
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down…")
        srv.shutdown()


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    e = Engine()
    if cmd == "rule":
        print(json.dumps(e.rule(rest[0]), indent=2, ensure_ascii=False))
    elif cmd == "keyword":
        print(json.dumps(e.keyword(rest[0]), indent=2, ensure_ascii=False))
    elif cmd == "glossary":
        print(json.dumps(e.glossary(" ".join(rest)), indent=2, ensure_ascii=False))
    elif cmd == "search":
        print(json.dumps(e.search(" ".join(rest)), indent=2, ensure_ascii=False))
    elif cmd == "turn-structure":
        print(json.dumps(e.turn_structure(), indent=2, ensure_ascii=False))
    elif cmd == "validate-log":
        print(json.dumps(e.validate_game_log(rest[0]), indent=2))
    elif cmd == "stats":
        print(json.dumps(e.stats(), indent=2))
    elif cmd == "serve":
        serve(int(rest[0]) if rest else 8484)
    else:
        print(f"unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
