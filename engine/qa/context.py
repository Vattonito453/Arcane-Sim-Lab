"""The run context every QA detector reads (repair plan WS1 task 1).

`ctx` is built ONCE per run and handed to each detector's detect(ctx). It
holds everything a detector may need, already parsed, so no detector re-reads
a 2 MB result file or re-derives which seat was piloted by what:

  games      one Game per game: players, result, zone records, agent events,
             the Forge log flattened in order, and who was active each turn
  pilots     per game, per player: "plan" | "stock" | None (unknown)
  plans      deck name -> plan (the JSON deck_plan wrote for the shim), when
             the plans file can be found; {} otherwise
  facts      the warm Scryfall card cache, read-only (never fetches)
  forge      the Forge index (engine/forge_index.py), or None when not built;
             it is Forge-derived, so it exists only at runtime, never in git
  board(i)   board.build() for game i, computed on first use

Sources, in the order a caller has them:
  from_result(path)   an adapted result file (sim_*.json, or a copy of one);
                      finds the raw shim JSONL and the plans file next to it
  from_jsonl(paths)   raw shim JSONL (study cells, shim_raw_*.jsonl), adapted
                      here with shim_log_adapter so both paths yield the same
                      Game shape
  from_result_dict()  an already-loaded result

Flags anchor by (game, turn, player, agent_event_index) until the shim stamps
`seq` on agent events (WS1 task 7); `anchor()` builds that record. A flag's
game is 1-based (Game.number); Game.index and ctx.pilot(game, ...) are the
0-based position in ctx.games.

Stdlib only, like the rest of engine/.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

SEAT_RE = re.compile(r"^Ai\((\d+)\)-")

# Zone-record phase names (Forge's PhaseType), in turn order. Everything before
# MAIN2 on the caster's own turn is "before main phase 2".
PHASES_BEFORE_MAIN2 = frozenset({
    "UNTAP", "UPKEEP", "DRAW", "MAIN1", "COMBAT_BEGIN", "COMBAT_DECLARE_ATTACKERS",
    "COMBAT_DECLARE_BLOCKERS", "COMBAT_FIRST_STRIKE_DAMAGE", "COMBAT_DAMAGE", "COMBAT_END",
})
PHASES_MAIN2_OR_LATER = frozenset({"MAIN2", "END_OF_TURN", "CLEANUP"})


def strip_seat(player: str | None) -> str:
    """"Ai(2)-Kess, Reanimator" -> "Kess, Reanimator" (the deck name)."""
    return SEAT_RE.sub("", player or "")


def seat_number(player: str | None) -> int | None:
    m = SEAT_RE.match(player or "")
    return int(m.group(1)) if m else None


def anchor(game: int, turn: int | None, player: str | None, agent_event_index: int | None,
           seq: int | None = None) -> dict:
    """Where a flag points: (game, turn, player, agent_event_index) until agent
    events carry the shim's `seq` (WS1 task 7), then seq as well.

    `game` is 1-BASED (Game.number), the numbering every QA detector's flags
    use: /results/{file}/game/{n} serves games[n-1], qa.knockouts numbers
    games from 1, and people say "game 1". agent_event_index is 0-based into
    that game's agent_events."""
    return {"game": game, "turn": turn, "player": player,
            "agent_event_index": agent_event_index, "seq": seq}


# ------------------------------------------------------------- card facts --

class CardFacts:
    """Read-only view of the Scryfall card cache (engine/cards.py's file).

    Never fetches: the QA layer runs after the sim, often on a box with no
    network, and a detector must not change what it measures by warming a
    cache. A card the cache does not hold is simply unknown."""

    def __init__(self, cache: dict | None = None, path: str | None = None) -> None:
        self.cache = cache if cache is not None else {}
        self.path = path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CardFacts":
        import cards
        p = Path(path) if path else cards.CACHE_PATH
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return cls({k: v for k, v in data.items() if isinstance(v, dict)}, str(p))

    @staticmethod
    def key(name: str) -> str:
        import cards
        return cards.key(name or "")

    def get(self, name: str | None) -> dict | None:
        if not name:
            return None
        c = self.cache.get(self.key(name))
        if c is None and " // " in name:
            c = self.cache.get(self.key(name.split(" // ")[0]))
        if not isinstance(c, dict) or c.get("not_found"):
            return None
        return c

    def type_line(self, name: str) -> str:
        """Front-face type line ("Instant // Land" -> "Instant")."""
        c = self.get(name) or {}
        return (c.get("type_line") or "").split(" // ")[0].strip()

    def oracle(self, name: str) -> str:
        return (self.get(name) or {}).get("oracle_text") or ""

    def cmc(self, name: str) -> float | None:
        c = self.get(name)
        v = c.get("cmc") if c else None
        return float(v) if isinstance(v, (int, float)) else None

    def colors(self, name: str) -> set[str] | None:
        c = self.get(name)
        if c is None or c.get("colors") is None:
            return None
        return set(c.get("colors") or [])

    def power(self, name: str) -> int | None:
        c = self.get(name)
        try:
            return int(c.get("power")) if c else None
        except (TypeError, ValueError):
            return None

    def mana_cost(self, name: str) -> str | None:
        c = self.get(name)
        return c.get("mana_cost") if c else None


# ------------------------------------------------------------ Forge index --

def load_forge_index(index_dir: str | Path | None = None):
    """The Forge index for this machine (or the one at index_dir), or None.

    The index is Forge-derived (GPL card scripts), so it is generated at
    runtime by engine/forge_index.py and never committed."""
    import forge_index as fi
    if index_dir is None:
        return fi.load_index()
    d = Path(index_dir)
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        cards_ = json.loads((d / "cards.json").read_text(encoding="utf-8"))["cards"]
        flags = json.loads((d / "flags.json").read_text(encoding="utf-8"))["flags"]
    except (OSError, ValueError, KeyError):
        return None
    return fi.ForgeIndex(d, meta, cards_, flags)


# ------------------------------------------------------------------ plans --

def load_plans(source) -> tuple[dict, dict]:
    """(deck name -> plan, info) from a plans file path or an already-loaded
    dict. info carries the file's planVersion (absent before the hotfix
    plan data, which is behind planVersion 2) and where it came from."""
    if source is None:
        return {}, {"path": None, "planVersion": None}
    if isinstance(source, dict):
        data, path = source, None
    else:
        path = str(source)
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}, {"path": path, "planVersion": None, "error": "unreadable"}
    decks = data.get("decks", data) if isinstance(data, dict) else {}
    decks = {k: v for k, v in decks.items() if isinstance(v, dict)}
    return decks, {"path": path, "planVersion": data.get("planVersion")}


def plan_version(plan: dict | None, info: dict | None = None) -> int:
    """The plan's version: a per-deck `planVersion` wins over the file's."""
    for src in (plan or {}, info or {}):
        v = src.get("planVersion")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return 1


def find_plans(path: str | Path) -> Path | None:
    """The plans file a run was piloted with, when it sits where the tools
    that wrote it put it.

    Production: run_sim writes plans_<stamp>_<run id>.json beside the result
    sim_<stamp>_<run id>[_rotated].json. Studies: plans_<pod>.json in the
    run's directory, a plans/ subdirectory, or the parent, where <pod> is a
    whole "_"-separated part of the run file's name (plans_a.json does not
    match every name holding an "a"). With no name match, a directory holding
    exactly one plans file is taken to be that run's, except for a result
    whose name carries a run id: that run's plans are its own or none, never
    the one plans file another run left in engine/sim_results."""
    p = Path(path)
    stem = p.name.split(".")[0]
    m = re.match(r"^sim_\d{8}_\d{6}_([A-Za-z0-9_-]+?)(?:_rotated)?$", stem)
    has_run_id = bool(m and m.group(1) != "rotated")
    if has_run_id:
        hits = sorted(p.parent.glob(f"plans_*_{m.group(1)}.json"))
        if hits:
            return hits[-1]

    def names_pod(c: Path) -> bool:
        pod = c.stem[len("plans_"):]
        return bool(pod) and re.search(rf"(?:^|_){re.escape(pod)}(?:_|$)", stem) is not None

    for d in (p.parent, p.parent / "plans", p.parent.parent):
        if not d.is_dir():
            continue
        cands = sorted(d.glob("plans_*.json"))
        named = [c for c in cands if names_pod(c)]
        if named:
            return max(named, key=lambda c: len(c.stem))
        if d == p.parent and len(cands) == 1 and not has_run_id:
            return cands[0]
    return None


# ------------------------------------------------------------------ games --

class Game:
    """One game, normalised from an adapted result's game dict."""

    def __init__(self, index: int, raw: dict) -> None:
        self.index = index
        self.raw = raw
        self.players: list[str] = list(raw.get("players") or [])
        self.result: dict = raw.get("result") or {}
        self.zones: list[dict] = list(raw.get("zones") or [])
        self.agent_events: list[dict] = list(raw.get("agent_events") or [])
        self.active: dict[int, str] = {}
        # (turn, event) in log order; event keeps the adapter's seq/action/raw.
        self.log: list[tuple[int, dict]] = []
        for t in raw.get("turns") or []:
            n = t.get("turn")
            if isinstance(n, int) and t.get("active_player"):
                self.active[n] = t["active_player"]
            for e in t.get("events") or []:
                self.log.append((n, e))

    @property
    def number(self) -> int:
        """1-based game number, for flags and anything a person reads
        (`index` stays 0-based: it is the position in ctx.games)."""
        return self.index + 1

    @property
    def winner(self) -> str | None:
        return self.result.get("winner")

    def has_zones(self) -> bool:
        return bool(self.zones)


# ---------------------------------------------------------------- context --

class RunContext:
    def __init__(self, result: dict, *, source: str | None = None,
                 plans=None, facts: CardFacts | None = None, forge=None,
                 raw_paths: list[str] | None = None) -> None:
        self.source = source
        self.result = result
        self.meta: dict = result.get("meta") or {}
        self.games = [Game(i, g) for i, g in enumerate(result.get("games") or [])]
        self.plans, self.plans_info = load_plans(plans)
        self.facts = facts if facts is not None else CardFacts.load()
        self.forge = forge
        self.raw_paths = list(raw_paths or [])
        self._pilots = self._pilot_map()
        self._boards: dict[int, tuple] = {}

    # -- seats --------------------------------------------------------------

    def _pilot_map(self) -> list[dict[str, str | None]]:
        """Per game, player -> "plan" | "stock" | None.

        A rotated result carries each rotation's agents (positional by seat)
        under meta.rotations_detail, with games stored rotation by rotation;
        a single-rotation result carries meta.agents. Seat k of "Ai(k)-Name"
        is position k-1 in either list."""
        meta = self.meta
        rot_agents: list[list] = []
        counts = meta.get("games_per_rotation_played") or meta.get("games_per_rotation_expected")
        detail = meta.get("rotations_detail") or []
        if detail and counts and len(counts) == len(detail):
            for r, n in enumerate(counts):
                rot_agents += [detail[r].get("agents") or []] * int(n or 0)
        flat = meta.get("agents") or []
        out: list[dict[str, str | None]] = []
        for g in self.games:
            agents = rot_agents[g.index] if g.index < len(rot_agents) else flat
            m: dict[str, str | None] = {}
            for p in g.players:
                k = seat_number(p)
                a = agents[k - 1] if k and 0 < k <= len(agents) else None
                m[p] = "stock" if a == "stock" else ("plan" if a else None)
            out.append(m)
        return out

    def pilot(self, game: int, player: str) -> str | None:
        if 0 <= game < len(self._pilots):
            return self._pilots[game].get(player)
        return None

    def deck(self, player: str) -> str:
        return strip_seat(player)

    def plan_for(self, player: str) -> dict | None:
        return self.plans.get(strip_seat(player))

    def commanders(self, player: str) -> set[str]:
        plan = self.plan_for(player) or {}
        return {c for c, r in (plan.get("roles") or {}).items() if r == "commander"}

    # -- lazy extras ----------------------------------------------------------

    def board(self, game: int):
        """board.build() for one game (zone stream when present), cached."""
        if game not in self._boards:
            import board as board_mod
            self._boards[game] = board_mod.build(self.games[game].raw, fetch=False)
        return self._boards[game]

    def basis(self) -> dict:
        """What this context was built from, for a detector's metrics."""
        return {
            "source": self.source,
            "agent": self.meta.get("agent"),
            "games": len(self.games),
            "zones": sum(1 for g in self.games if g.has_zones()),
            "plans": self.plans_info.get("path") or (bool(self.plans) or None),
            "planVersion": self.plans_info.get("planVersion"),
            "forge_index": getattr(self.forge, "version", None),
            "card_cache": len(self.facts.cache),
            "raw_jsonl": len(self.raw_paths),
        }


# ---------------------------------------------------------------- builders --

def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _raw_logs_for(path: Path) -> list[Path]:
    try:
        import readapt
    except Exception:  # noqa: BLE001 - optional nicety, never fatal
        return []
    rid = readapt.run_id_of(Path(path.name.replace(".json.out", ".json")))
    return readapt.raw_logs_for(path, rid) if rid else []


def _adapt_jsonl(paths: list[Path]) -> dict:
    """Adapt one or more raw shim JSONL files into one result dict. Several
    files are several rotations: their games are concatenated and each
    rotation's agents recorded the way run_sim records them."""
    from shim_log_adapter import parse_shim_jsonl
    games: list = []
    detail: list = []
    counts: list = []
    meta: dict = {}
    for p in paths:
        sub = parse_shim_jsonl(p.read_text(encoding="utf-8", errors="replace"), source=str(p))
        meta = meta or dict(sub.get("meta") or {})
        games += sub.get("games") or []
        detail.append({"agents": (sub.get("meta") or {}).get("agents") or []})
        counts.append(len(sub.get("games") or []))
    if len(paths) > 1:
        meta["rotations_detail"] = detail
        meta["games_per_rotation_played"] = counts
    return {"meta": meta, "games": games}


def from_result_dict(result: dict, **kw) -> RunContext:
    return RunContext(result, **kw)


def from_result(path: str | Path, *, plans=None, facts: CardFacts | None = None,
                forge=None, find_plans_file: bool = True) -> RunContext:
    """Context for an adapted result file. When the result predates the zone
    stream but its raw shim JSONL sits beside it, the games are re-adapted
    from the raw logs (the same re-parse readapt.py does)."""
    p = Path(path)
    result = _read_json(p)
    raw = _raw_logs_for(p)
    games = result.get("games") or []
    if raw and games and not any(g.get("zones") for g in games):
        fresh = _adapt_jsonl(raw)
        if len(fresh["games"]) == len(games):
            result = dict(result, games=fresh["games"])
    if plans is None and find_plans_file:
        plans = find_plans(p)
    return RunContext(result, source=str(p), plans=plans, facts=facts, forge=forge,
                      raw_paths=[str(r) for r in raw])


def from_jsonl(paths, *, plans=None, facts: CardFacts | None = None, forge=None,
               find_plans_file: bool = True) -> RunContext:
    """Context for raw shim JSONL (one file, or one file per rotation)."""
    ps = [Path(paths)] if isinstance(paths, (str, Path)) else [Path(x) for x in paths]
    result = _adapt_jsonl(ps)
    if plans is None and find_plans_file:
        plans = find_plans(ps[0])
    return RunContext(result, source=str(ps[0]) if len(ps) == 1 else ";".join(str(x) for x in ps),
                      plans=plans, facts=facts, forge=forge, raw_paths=[str(x) for x in ps])


def from_path(path: str | Path, **kw) -> RunContext:
    """from_jsonl for *.jsonl, from_result for anything else."""
    return (from_jsonl if str(path).endswith(".jsonl") else from_result)(path, **kw)
