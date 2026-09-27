#!/usr/bin/env python3
"""tutors: did the pilot's tutors find what they were cast for? (rules-determined)

Repair plan WS1 task 1 (the `tutors` row), measuring WS5's tutoring targets
and their guards (tasks/25-repair-plan.md §3.0, §4.4 G0a). Ported from the
2026-09 diagnosis prototypes: combo_execution/tutor_reach.py and
verify/tutor_restrictions/ (reach), tutoring/parse_tutors.py and miss_reason.py
(what the search offered and why a piece was missed), tutoring/gate_state.py
(plan tutors per seat), verify/tutorreach/ (X and failed-to-target fates),
forge_leverage/scripts/tutorphase.py and tutorpick.py, verify/tutor_main2/
(phase, pick type, fetched card used the same turn), research_meta/
tutor_timing.py (casts per tutor drawn) and verify/portal_override/ (closer
overrides).

What it measures, per seat (deck x pilot), per pilot and pooled:

  tutor_cast            shim `tutor_cast X seeking Y` events (the plan's own
                        decision to tutor for a line's missing piece)
  unreachable           of those, casts that could not find Y. Evidence, best
                        first: the shim's own `reach=` (0.17.0+, Forge's
                        Card.isValid at decision time); else Forge's search,
                        when it resolved with Y as the missing piece (offered
                        or not); else where Y was (not in the library) and
                        the tutor's ChangeType read from the Forge index
  restriction_excludes  casts whose tutor's own search restriction cannot
                        include Y, from the Forge index alone. This is the
                        diagnosis figure (316/718) the port test reproduces
  seeking_gy_exile      casts seeking a piece already in graveyard or exile
                        (as of the cast itself)
  searched / _not_offered  casts whose search resolved, and of those the ones
                        whose offer did not hold the line's missing piece
  x_zero / x_resolved   casts that resolved with X=0, of those that showed X
  failed_to_target      casts Forge refused to put on the stack
  cast_never_searches   casts of a card whose search is a keyword (transmute,
                        typecycling) or activated ability: casting the spell
                        never searches
  gy_searches, gy_steers_*  graveyard-destination searches, whether they still
                        picked a card (the guard), and the plan's steers: onto
                        a card with no use in the graveyard (the defect) or
                        onto a reanimation target / card castable from the
                        graveyard (expected; reported, not penalised)

Over every tutor SPELL a seat casts from hand (its plan's `tutors` minus its
commanders; without a plan, cards whose search can find a nonland card),
whoever decided the cast:

  phase                 per kind (a spell's destination: hand, library_top,
                        battlefield, graveyard, exile; "permanent" for a
                        permanent that searches once it has resolved;
                        "keyword_only" for a transmute card cast as a spell):
                        own_/opp_ turn x before_main2 /
                        main2_or_later, or unknown on logs without phase.
                        Rates: before_main2 (phase before MAIN2 on either
                        turn: the diagnosis's 0/269) and timely (adds any
                        opponent-turn cast: WS5 T3's end-step window)
  pick_types            primary type of each fetched card; generic_picks for
                        unrestricted ("Card") tutors to hand
  fetch_use             hand and library-top fetches used the same turn
  closer_seen/overrides searches where stock picked a proven closer, and how
                        often the plan steered away from it
  casts_per_drawn       the guard: tutor spells cast from hand per tutor
                        drawn. Commanders recast from the command zone are
                        not tutors drawn, so they are not counted (the
                        diagnosis's 594/892 counted them; from hand it is
                        544/892 on the same stock seats)

Flags are per-moment records {game, turn, player, kind, detail, anchor}
anchored at (game, turn, player, agent_event_index) until agent events
carry `seq`.

Nothing here decides what happened in a game: Forge's log, its zone stream
and its own search offers say that. The Forge index read (ChangeType) is
used to classify a cast, never to replay one.

CLI:
    py engine/qa/tutors.py <result.json | shim.jsonl ...> [--plans P]
        [--card-cache C] [--forge-index DIR] [--flags]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from qa.context import (  # noqa: E402
    PHASES_BEFORE_MAIN2, PHASES_MAIN2_OR_LATER, anchor, plan_version, strip_seat,
)

NAME = "tutors"
KIND = "rules"

# WS5 T2 names the proven-closer class "Portal-class, Craterhoof". Until the
# owner tags (WS8 sidecar) exist, these two are the closers; a plan may extend
# the set with a `closers` list (top level or under `search`).
PROVEN_CLOSERS = frozenset({"Portal to Phyrexia", "Craterhoof Behemoth"})

# ------------------------------------------------------------ ChangeType --

_PERMANENT = {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}
_COLOR_WORDS = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}
# Clauses that pick among cards an earlier step chose (Intuition, Gifts,
# "the chosen name"): not a type search, so they say nothing about reach.
_DYNAMIC_BASES = {"Remembered", "Targeted", "Triggered", "TargetedCard", "ChosenCard",
                  "Imprinted", "Defined", "EnchantedBy", "Equipped", "EACH"}
_DYNAMIC_QUAL = re.compile(r"^(IsRemembered|Remembered|IsImprinted|Imprinted|NamedCard|"
                           r"ChosenCard|sameName|named|NotedName|IsTargeted|Triggered)")
_IGNORED_QUAL = {"", "YouOwn", "YouCtrl", "OppOwn", "OppCtrl", "Other", "nonToken",
                 "YouDontCtrl", "notSameName"}
_CMP = re.compile(r"^(cmc|power|toughness)(LE|LT|GE|GT|EQ|NE)(.+)$")
_MANACOST = re.compile(r"^ManaCost(\d+)$")
_TYPE_WORD = re.compile(r"^[A-Z][A-Za-z'\-]*$")
_LAND_BASES = {"Land", "Basic", "Forest", "Island", "Mountain", "Plains", "Swamp",
               "Desert", "Gate", "Town", "Cave", "Sphere", "Lair", "Locus", "Mine", "Tower"}
_OPS = {"LE": lambda a, b: a <= b, "LT": lambda a, b: a < b, "GE": lambda a, b: a >= b,
        "GT": lambda a, b: a > b, "EQ": lambda a, b: a == b, "NE": lambda a, b: a != b}

COND = "cond"   # reachable depending on X, the board or a fact we lack
SKIP = "skip"   # a clause that is not a type search


def _tokens(types: str) -> set[str]:
    """Type-line words: Forge's "Legendary Creature Human Wizard", or
    Scryfall's, which puts a dash (U+2014) before the subtypes. Hyphenated
    subtypes (Assembly-Worker) stay whole."""
    return set((types or "").replace("\u2014", " ").split())


def _qual(q: str, f: dict, tutor_cmc: float | None):
    """True / False / None(unknown) for one qualifier of a ChangeType clause."""
    if q in _IGNORED_QUAL:
        return True
    if q.startswith("!"):
        r = _qual(q[1:], f, tutor_cmc)
        return None if r is None else not r
    if q.startswith("non") and len(q) > 3 and q[3].isupper():
        r = _qual(q[3:], f, tutor_cmc)
        return None if r is None else not r
    if q in _COLOR_WORDS:
        return None if f["colors"] is None else _COLOR_WORDS[q] in f["colors"]
    if q == "Colorless":
        return None if f["colors"] is None else not f["colors"]
    if q == "Multicolor":
        return None if f["colors"] is None else len(f["colors"]) > 1
    if q == "MonoColor":
        return None if f["colors"] is None else len(f["colors"]) == 1
    if q == "Permanent":
        return bool(f["tokens"] & _PERMANENT)
    if q == "sameCMC":
        if f["cmc"] is None or tutor_cmc is None:
            return None
        return f["cmc"] == tutor_cmc
    m = _CMP.match(q)
    if m:
        stat, op, val = m.groups()
        have = f["cmc"] if stat == "cmc" else f.get(stat)
        if have is None or not val.isdigit():
            return None     # X, Y or an SVar: decided at cast time
        return _OPS[op](have, int(val))
    m = _MANACOST.match(q)
    if m:
        return None if f["cmc"] is None else f["cmc"] == int(m.group(1))
    if _TYPE_WORD.match(q):
        return q in f["tokens"]
    return None


def is_type_search(clause: str) -> bool:
    """False for a clause that picks among cards an earlier step chose."""
    clause = clause.strip()
    if not clause:
        return False
    base, _, rest = clause.partition(".")
    quals = [q.strip() for q in rest.split("+")] if rest else []
    return not (base in _DYNAMIC_BASES or " " in base or any(_DYNAMIC_QUAL.match(q) for q in quals))


def clause_verdict(clause: str, f: dict, tutor_cmc: float | None = None):
    """True / COND / False / SKIP for one comma-separated ChangeType clause,
    e.g. "Creature.Green+cmcLEX", against a target's facts."""
    if not is_type_search(clause):
        return SKIP
    clause = clause.strip()
    base, _, rest = clause.partition(".")
    quals = [q.strip() for q in rest.split("+")] if rest else []
    if base in ("Card", "Any"):
        results = []
    elif base == "Permanent":
        results = [bool(f["tokens"] & _PERMANENT)]
    else:
        results = [_qual(base, f, tutor_cmc)]
    results += [_qual(q, f, tutor_cmc) for q in quals]
    if any(r is False for r in results):
        return False
    if any(r is None for r in results):
        return COND
    return True


def combine_verdicts(verdicts) -> object:
    vs = [v for v in verdicts if v is not SKIP]
    if not vs:
        return None
    if any(v is True for v in vs):
        return True
    if any(v == COND for v in vs):
        return COND
    return False


class Reach:
    """Tutor search facts from the Forge index, target facts from the Forge
    index (types) and the card cache (mana value, colours, power).

    `searches` and `types` override the index for tests: {name: [search]} in
    tutors.json's shape, {name: "Types line"}."""

    def __init__(self, forge=None, facts=None, searches: dict | None = None,
                 types: dict | None = None) -> None:
        self.forge = forge
        self.facts = facts
        self._searches = searches
        self._types = types
        self._memo: dict = {}

    @property
    def available(self) -> bool:
        return self._searches is not None or self.forge is not None

    def _forge_name(self, name: str) -> str | None:
        if self.forge is None:
            return None
        return self.forge.resolve(name)

    def searches(self, tutor: str) -> list | None:
        if self._searches is not None:
            return self._searches.get(tutor)
        fname = self._forge_name(tutor)
        if not fname:
            return None
        return self.forge.tutors().get(fname)

    def target_facts(self, name: str) -> dict | None:
        key = ("facts", name)
        if key in self._memo:
            return self._memo[key]
        types = ""
        if self._types is not None:
            types = self._types.get(name, "")
        elif self.forge is not None:
            fname = self._forge_name(name)
            types = self.forge.types(fname) if fname else ""
        if not types and self.facts is not None:
            types = self.facts.type_line(name)
        out = None
        if types:
            fc = self.facts
            out = {"tokens": _tokens(types),
                   "cmc": fc.cmc(name) if fc else None,
                   "colors": fc.colors(name) if fc else None,
                   "power": fc.power(name) if fc else None,
                   "toughness": None}
        self._memo[key] = out
        return out

    def restriction(self, tutor: str, target: str):
        """(verdict, change types) where verdict is True, COND, False or None
        (unknown tutor, unknown target, or only non-type searches)."""
        key = ("r", tutor, target)
        if key in self._memo:
            return self._memo[key]
        ss = self.searches(tutor)
        f = self.target_facts(target)
        if not ss or f is None:
            res = (None, [])
        else:
            tcmc = self.facts.cmc(tutor) if self.facts else None
            verdicts, cts = [], []
            for s in ss:
                ct = s.get("change_type") or ""
                clauses = ct.split(",")
                verdicts += [clause_verdict(c, f, tcmc) for c in clauses]
                if any(is_type_search(c) for c in clauses):
                    cts.append(ct)
            res = (combine_verdicts(verdicts), cts)
        self._memo[key] = res
        return res

    def dest_kind(self, tutor: str) -> str | None:
        """Where the tutor puts what it finds: hand, library_top, battlefield,
        graveyard, exile (library for a search that stays in the library)."""
        ss = [s for s in (self.searches(tutor) or [])
              if any(is_type_search(c) for c in (s.get("change_type") or "Card").split(","))]
        if not ss:
            return None
        s = ss[0]
        dest = (s.get("destination") or "").split(",")[0].strip()
        if dest == "Library":
            if str(s.get("library_position", "")) == "0":
                return "library_top"
            others = {(x.get("destination") or "") for x in (self.searches(tutor) or [])}
            return "hand" if "Hand" in others else "library"
        return dest.lower() or None

    def cast_mode(self, tutor: str) -> str | None:
        """"spell" when casting the card searches (its spell, or a trigger
        such as an ETB); "keyword" when the search is only a keyword ability
        (transmute, typecycling); "activated" when only an activated ability
        searches. None when the card has no search in the index."""
        ss = self.searches(tutor)
        if not ss:
            return None
        vias = set()
        for s in ss:
            via = s.get("via")
            if via == "K":
                vias.add("keyword")
            elif via == "AB" and not s.get("svar"):
                vias.add("activated")
            else:
                vias.add("spell")
        if "spell" in vias:
            return "spell"
        return "keyword" if "keyword" in vias else "activated"

    def generic(self, tutor: str) -> bool:
        """A search restricted by nothing ("Card"): Demonic Tutor, Gamble."""
        ss = self.searches(tutor) or []
        return bool(ss) and (ss[0].get("change_type") or "").strip() == "Card"

    def nonland_tutor(self, name: str) -> bool:
        """Can this card's search (cast or triggered) find a nonland card?"""
        for s in self.searches(name) or []:
            if s.get("via") == "AB" and not s.get("svar"):
                continue
            for clause in (s.get("change_type") or "").split(","):
                base = clause.strip().split(".")[0]
                if is_type_search(clause) and base not in _LAND_BASES:
                    return True
        return False


# --------------------------------------------------------- graveyard use --

_SELF_GY = re.compile(r"\b(flashback|escape|unearth|retrace|jump-start|embalm|eternalize|"
                      r"disturb|encore|aftermath)\b", re.I)
_REANIMATE = (
    re.compile(r"\b(?:return|put)s?\b[^.]*?\bcreature cards?\b[^.]*?\bgraveyards?\b[^.]*?"
               r"\b(?:to|onto) the battlefield", re.I),
    re.compile(r"\breturn enchanted creature card to the battlefield", re.I),
    re.compile(r"\bcreature cards? from (?:their|your|a|all) graveyards?\b[^.]*?\bputs?\b[^.]*?"
               r"onto the battlefield", re.I),
)
_CMD_GY = (
    re.compile(r"\bcast (?:an? |one |target )?(?P<what>[a-z ,]+?) (?:card|spell)s? from your graveyard",
               re.I),
    re.compile(r"\bcast an? (?P<what>[a-z]+) spell of each [a-z ]+ from your graveyard", re.I),
)
_GY_TYPES = ("instant", "sorcery", "creature", "artifact", "enchantment", "planeswalker",
             "land", "battle")


def _self_castable_from_gy(name: str, oracle: str) -> bool:
    if _SELF_GY.search(oracle):
        return True
    low = oracle.lower()
    me = name.lower()
    return any(p in low for p in (f"cast {me} from your graveyard", "cast this card from your graveyard",
                                  f"play {me} from your graveyard",
                                  f"return {me} from your graveyard to the battlefield"))


def _commander_gy_types(oracle: str) -> set[str]:
    out: set[str] = set()
    for rx in _CMD_GY:
        for m in rx.finditer(oracle):
            what = m.group("what").lower()
            out |= {t for t in _GY_TYPES if t in what}
            if "permanent" in what:
                out |= {"creature", "artifact", "enchantment", "planeswalker", "land", "battle"}
    return out


# ---------------------------------------------------------------- parsing --

_TC = re.compile(r"^(?P<tutor>.+?) seeking (?P<want>.+)$")
_KV_TAIL = re.compile(r"\s+([A-Za-z]\w*)=(\S*)$")
_SS = re.compile(r"^(?P<head>.*?) missing=(?P<missing>.*) picked=(?P<picked>.*) "
                 r"planPick=(?P<planPick>.*) src=(?P<src>.*)$")
_STEER = re.compile(r"^sid=(\d+) mode=(\S+) value=(-?\d+) stockValue=(-?\d+) steer=(.*) over=(.*)$")
_FAILED = re.compile(r"^(?P<card>.+?) \((?P<id>\d+)\) - \[Couldn't add to stack, (?P<why>[^\]]*)\]")
_RESOLVE = re.compile(r"^(?P<card>.+?)(?: \((?P<id>\d+)\))?(?: - |$)")
_X = re.compile(r"\(X=(\d+)\)\s*$")


def parse_tutor_cast(detail: str) -> dict | None:
    """"Worldly Tutor seeking Felidar Guardian[ reach=false ...]"."""
    m = _TC.match(detail or "")
    if not m:
        return None
    want, kv = m.group("want"), {}
    while True:
        t = _KV_TAIL.search(want)
        if not t:
            break
        kv[t.group(1)] = t.group(2)
        want = want[:t.start()]
    reach = kv.get("reach")
    return {"tutor": m.group("tutor"), "want": want.strip(),
            "reach": True if reach == "true" else (False if reach == "false" else None),
            "kv": kv}


def parse_search_seen(detail: str) -> dict:
    m = _SS.match(detail or "")
    out: dict = {}
    head = detail or ""
    if m:
        head = m.group("head")
        out.update(missing=m.group("missing"), picked=m.group("picked"),
                   planPick=m.group("planPick"), src=m.group("src"))
    for tok in head.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def parse_steer(detail: str) -> dict | None:
    m = _STEER.match(detail or "")
    if not m:
        return None
    return dict(zip(("sid", "mode", "value", "stockValue", "steer", "over"), m.groups()))


def primary_type(types: str) -> str:
    """Forge zone records list core types comma-joined ("Creature,Artifact");
    type lines use spaces. Either way, one primary type per card."""
    t = set(re.split(r"[,\s]+", types or "")) - {""}
    for k in ("Creature", "Land", "Planeswalker", "Artifact", "Enchantment", "Instant",
              "Sorcery", "Battle"):
        if k in t:
            return k
    return "Other" if t else "Unknown"


# ------------------------------------------------------------- aggregation --

def new_bucket() -> dict:
    return {
        "tutor_cast": 0, "unreachable": 0, "unreachable_reasons": {}, "reach_basis": {},
        "restriction_excludes": 0, "restriction_conditional": 0, "restriction_unknown": 0,
        "seeking_gy_exile": 0, "searched": 0, "searched_not_offered": 0,
        "x_resolved": 0, "x_zero": 0, "failed_to_target": 0, "cast_never_searches": {},
        "tutors_drawn": 0, "tutor_spells_cast": 0, "tutor_spells_cast_by_shim": 0,
        "phase": {}, "pick_types": {}, "generic_picks": 0, "generic_picks_creature": 0,
        "fetch_use": {},
        "gy_searches": 0, "gy_searches_picked": 0, "gy_steers": 0,
        "gy_steers_no_use": 0, "gy_steers_graveyard_use": 0, "gy_steers_unknown": 0,
        "gy_steer_cards": {"no_use": {}, "graveyard_use": {}, "unknown": {}},
        "closer_seen": 0, "closer_overrides": 0,
    }


def _add(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict):
            _add(dst.setdefault(k, {}), v)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            dst[k] = dst.get(k, 0) + v


def _inc(d: dict, *path, n: int = 1) -> None:
    for k in path[:-1]:
        d = d.setdefault(k, {})
    d[path[-1]] = d.get(path[-1], 0) + n


def _rate(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def _phase_rates(kinds) -> tuple:
    """Two readings of "cast before main phase 2", from the same buckets:

    before_main2  the phase was before MAIN2, on whoever's turn it was: the
                  diagnosis's reading (stock library-top tutors 0/269).
    timely        own turn before MAIN2, or any time on an opponent's turn:
                  WS5 T3's tutor window (an opponent's end step, or upkeep).
    """
    before = timely = total = 0
    for kind in kinds:
        early = kind.get("own_before_main2", 0) + kind.get("opp_before_main2", 0)
        before += early
        timely += early + kind.get("opp_main2_or_later", 0)
        total += sum(v for k, v in kind.items() if k != "unknown")
    return _rate(before, total), _rate(timely, total)


def finalize(bucket: dict) -> dict:
    """Ratios from counts (idempotent; recomputed after every combine)."""
    b = bucket
    b["unreachable_rate"] = _rate(b.get("unreachable", 0), b.get("tutor_cast", 0))
    b["restriction_rate"] = _rate(b.get("restriction_excludes", 0), b.get("tutor_cast", 0))
    b["casts_per_drawn"] = _rate(b.get("tutor_spells_cast", 0), b.get("tutors_drawn", 0))
    phase = b.get("phase") or {}
    b["before_main2_rate"], b["timely_rate"] = _phase_rates(phase.values())
    lt = [phase["library_top"]] if "library_top" in phase else []
    b["library_top_before_main2_rate"], b["library_top_timely_rate"] = _phase_rates(lt)
    used = n = 0
    for v in (b.get("fetch_use") or {}).values():
        used += v.get("used_same_turn", 0)
        n += v.get("fetched", 0)
    b["fetched_used_same_turn_rate"] = _rate(used, n)
    return b


def _strip_ratios(b: dict) -> dict:
    return {k: v for k, v in b.items() if not (k.endswith("_rate") or k == "casts_per_drawn")}


def combine(results: list[dict]) -> dict:
    """Sum several detect() metrics (one per run file) into one."""
    out = {"detector": NAME, "kind": KIND, "basis": [], "pooled": new_bucket(),
           "by_pilot": {}, "by_seat": {}}
    for r in results:
        out["basis"].append(r.get("basis"))
        _add(out["pooled"], _strip_ratios(r.get("pooled") or {}))
        for pilot, b in (r.get("by_pilot") or {}).items():
            _add(out["by_pilot"].setdefault(pilot, new_bucket()), _strip_ratios(b))
        for deck, per in (r.get("by_seat") or {}).items():
            for pilot, b in per.items():
                _add(out["by_seat"].setdefault(deck, {}).setdefault(pilot, new_bucket()),
                     _strip_ratios(b))
    finalize(out["pooled"])
    for b in out["by_pilot"].values():
        finalize(b)
    for per in out["by_seat"].values():
        for b in per.values():
            finalize(b)
    return out


# ------------------------------------------------------------------ detect --

class _GameScan:
    """Indexes one game once so every per-cast lookup is cheap."""

    def __init__(self, g) -> None:
        self.g = g
        self.Z = g.zones
        self.owner: dict = {}
        self.by_name: dict[str, list[int]] = {}
        # (player, card name) -> that player's own card ids, so a resolution
        # "Card (id) - ..." is matched to the right caster when several seats
        # (or a copy) put the same card on the stack in one turn.
        self.ids: dict[tuple, set] = {}
        for i, z in enumerate(self.Z):
            cid = z.get("cardId")
            if cid is not None and cid not in self.owner:
                self.owner[cid] = z.get("fromPlayer") or z.get("toPlayer")
            self.by_name.setdefault(z.get("card"), []).append(i)
            if cid is not None and not z.get("token"):
                for who in {z.get("fromPlayer"), z.get("toPlayer")} - {None, ""}:
                    self.ids.setdefault((who, z.get("card")), set()).add(cid)
        # Cast attempts per (player, card), in log order: Forge's "<player>
        # cast <card>" line, or its refusal "<card> (id) - [Couldn't add to
        # stack, <why>]", whose caster is the card id's owner.
        self.attempts: dict[tuple, list[dict]] = {}
        resolves: dict[str, list[tuple[int, int, str]]] = {}
        casts: list[dict] = []
        for pos, (turn, e) in enumerate(g.log):
            act = e.get("action")
            raw = e.get("raw") or ""
            if act == "stack_add":
                m = _FAILED.match(raw)
                if m:
                    p = self.owner.get(int(m.group("id")))
                    self.attempts.setdefault((p, m.group("card")), []).append(
                        {"turn": turn, "pos": pos, "card": m.group("card"),
                         "status": "failed", "why": m.group("why")})
                    continue
                for p in g.players:
                    if raw.startswith(p + " cast "):
                        card = e.get("object") or re.sub(r" targeting .*$", "",
                                                         raw[len(p) + 6:])
                        a = {"turn": turn, "pos": pos, "card": card, "player": p,
                             "status": "cast", "x": None}
                        self.attempts.setdefault((p, card), []).append(a)
                        casts.append(a)
                        break
            elif act == "stack_resolve":
                m = _RESOLVE.match(raw)
                if m:
                    rid = int(m.group("id")) if m.group("id") else None
                    resolves.setdefault(m.group("card"), []).append((pos, turn, raw, rid))
        # Each cast's own resolution: the next unclaimed resolve of that card
        # carrying one of the caster's own card ids, no later than the next
        # turn. Its "(X=n)" is the X Forge paid. A countered spell has none.
        claimed: set[int] = set()
        for a in casts:
            mine = self.ids.get((a["player"], a["card"])) or set()
            for pos, turn, raw, rid in resolves.get(a["card"], []):
                if pos <= a["pos"] or pos in claimed:
                    continue
                if isinstance(turn, int) and isinstance(a["turn"], int) and turn > a["turn"] + 1:
                    break
                if rid is not None and mine and rid not in mine:
                    continue
                claimed.add(pos)
                x = _X.search(raw)
                a["x"] = int(x.group(1)) if x else None
                a["resolved"] = True
                break

    def location(self, card: str, player: str, cut: int, default: str) -> str:
        loc = default
        for i in self.by_name.get(card, []):
            if i >= cut:
                break
            z = self.Z[i]
            if z.get("token"):
                continue
            if z.get("fromPlayer") == player or z.get("toPlayer") == player:
                loc = z.get("to") or loc
        return loc

    def first_after_turn(self, turn: int) -> int:
        for i, z in enumerate(self.Z):
            if (z.get("turn") or 0) > turn:
                return i
        return len(self.Z)


class _Detector:
    def __init__(self, ctx, reach: Reach | None = None) -> None:
        self.ctx = ctx
        self.reach = reach or Reach(forge=ctx.forge, facts=ctx.facts)
        self.flags: list[dict] = []
        self.buckets: dict[tuple, dict] = {}
        self._deck_reanimates: dict = {}
        self._tutor_sets: dict = {}

    # -- seat helpers ---------------------------------------------------------

    def bucket(self, game: int, player: str) -> dict:
        key = (strip_seat(player), self.ctx.pilot(game, player) or "unknown")
        if key not in self.buckets:
            self.buckets[key] = new_bucket()
        return self.buckets[key]

    def flag(self, game: int, turn, player, kind: str, detail: str, ai) -> None:
        self.flags.append({"game": game, "turn": turn, "player": player, "kind": kind,
                           "detail": detail, "anchor": anchor(game, turn, player, ai)})

    def tutor_set(self, player: str, scan: _GameScan) -> set[str] | None:
        """The seat's tutors: its plan's list minus its commanders; without a
        plan, every card it moved whose search can find a nonland card."""
        plan = self.ctx.plan_for(player)
        has_plan = bool(plan) and plan.get("tutors") is not None
        # A plan's list holds for the whole run; the fallback reads the cards
        # this seat moved, so it is per game.
        key = (strip_seat(player), None if has_plan else scan.g.index)
        if key in self._tutor_sets:
            return self._tutor_sets[key]
        if has_plan:
            s = set(plan.get("tutors") or []) - self.ctx.commanders(player)
        elif self.reach.available:
            seen = {z.get("card") for z in scan.Z
                    if z.get("fromPlayer") == player or z.get("toPlayer") == player}
            s = {c for c in seen if c and self.reach.nonland_tutor(c)}
        else:
            s = None
        self._tutor_sets[key] = s
        return s

    def closers(self, player: str) -> set[str]:
        plan = self.ctx.plan_for(player) or {}
        extra = plan.get("closers") or (plan.get("search") or {}).get("closers") or []
        return set(PROVEN_CLOSERS) | set(extra)

    def deck_cards(self, player: str, scan: _GameScan) -> set[str]:
        plan = self.ctx.plan_for(player) or {}
        cards = set(plan.get("roles") or {}) | set(plan.get("weights") or {})
        if not cards:
            cards = {z.get("card") for z in scan.Z
                     if (z.get("fromPlayer") == player or z.get("toPlayer") == player)
                     and not z.get("token")}
        return {c for c in cards if c}

    def reanimates(self, player: str, scan: _GameScan) -> bool | None:
        deck = strip_seat(player)
        if deck not in self._deck_reanimates:
            facts = self.ctx.facts
            known = False
            hit = False
            for c in self.deck_cards(player, scan):
                o = facts.oracle(c)
                if o:
                    known = True
                    if any(rx.search(o) for rx in _REANIMATE):
                        hit = True
                        break
            self._deck_reanimates[deck] = True if hit else (False if known else None)
        return self._deck_reanimates[deck]

    def graveyard_use(self, card: str, player: str, scan: _GameScan):
        """(True | False | None, why). Plan data first (planVersion 2's
        search.graveyardTargets); otherwise the same three rules WS5 T1 gives
        deck_plan: reanimation targets for decks that reanimate; flashback,
        escape, unearth (and kin) cards; instants and sorceries (or whatever
        type the text names) the commander can cast from the graveyard."""
        plan = self.ctx.plan_for(player) or {}
        search = plan.get("search") or {}
        if plan_version(plan, self.ctx.plans_info) >= 2 and "graveyardTargets" in search:
            gt = search.get("graveyardTargets") or {}
            if isinstance(gt, dict):
                v = gt.get(card)
                ok = isinstance(v, (int, float)) and v > 0
            else:
                ok = card in set(gt)
            return (True, "graveyard_target") if ok else (False, "not_a_graveyard_target")
        facts = self.ctx.facts
        oracle = facts.oracle(card)
        types = facts.type_line(card)
        if not types:
            f = self.reach.target_facts(card)
            types = " ".join(sorted(f["tokens"])) if f else ""
        if not types and not oracle:
            return None, "unknown_card"
        low_types = types.lower()
        if oracle and _self_castable_from_gy(card, oracle):
            return True, "castable_from_graveyard"
        for cmd in self.ctx.commanders(player):
            allowed = _commander_gy_types(facts.oracle(cmd))
            if allowed and any(t in low_types for t in allowed):
                return True, "commander_casts_from_graveyard"
        if "creature" in low_types:
            r = self.reanimates(player, scan)
            if r:
                return True, "reanimation_target"
            if r is None:
                return None, "deck_unknown"
        return False, "no_graveyard_use"

    # -- per game ---------------------------------------------------------------

    def run(self) -> None:
        for g in self.ctx.games:
            scan = _GameScan(g)
            self._tutor_casts(g, scan)
            self._searches(g, scan)
            self._tutor_spells(g, scan)

    def _link_search(self, g, ai: int, player: str, tutor: str, turn, claimed: set) -> tuple:
        for j in range(ai + 1, len(g.agent_events)):
            b = g.agent_events[j]
            bt = b.get("turn")
            if isinstance(bt, int) and isinstance(turn, int) and bt > turn + 1:
                break
            if j in claimed or b.get("event") != "search_seen" or b.get("player") != player:
                continue
            ss = parse_search_seen(b.get("detail"))
            if ss.get("src") == tutor:
                claimed.add(j)
                return j, ss
        return None, None

    def _tutor_casts(self, g, scan: _GameScan) -> None:
        claimed_ss: set[int] = set()
        claimed_attempt: set[int] = set()
        claimed_zone: set[int] = set()
        for ai, a in enumerate(g.agent_events):
            if a.get("event") != "tutor_cast":
                continue
            tc = parse_tutor_cast(a.get("detail"))
            if not tc:
                continue
            p, t = a.get("player"), a.get("turn")
            tutor, want = tc["tutor"], tc["want"]
            b = self.bucket(g.index, p)
            b["tutor_cast"] += 1

            # The cast itself, in Forge's log: a stack add (or a refusal).
            attempt = None
            for tt in (t, (t + 1) if isinstance(t, int) else None):
                for att in scan.attempts.get((p, tutor), []):
                    if id(att) in claimed_attempt or att["turn"] != tt:
                        continue
                    attempt = att
                    break
                if attempt:
                    break
            if attempt:
                claimed_attempt.add(id(attempt))

            # Where the sought piece was when the tutor left the hand.
            cut = None
            for i in scan.by_name.get(tutor, []):
                z = scan.Z[i]
                if i in claimed_zone:
                    continue
                if z.get("turn") == t and z.get("from") in ("Hand", "Command") \
                        and z.get("to") == "Stack" and z.get("fromPlayer") == p:
                    cut = i
                    claimed_zone.add(i)
                    break
            if cut is None:
                cut = scan.first_after_turn(t if isinstance(t, int) else 0)
            default = "Command" if want in self.ctx.commanders(p) else "Library"
            loc = scan.location(want, p, cut, default)

            restr, cts = self.reach.restriction(tutor, want)
            if restr is False:
                b["restriction_excludes"] += 1
            elif restr == COND:
                b["restriction_conditional"] += 1
            elif restr is None:
                b["restriction_unknown"] += 1
            if loc in ("Graveyard", "Exile"):
                b["seeking_gy_exile"] += 1

            sj, ss = self._link_search(g, ai, p, tutor, t, claimed_ss)
            offered = None
            if ss is not None:
                b["searched"] += 1
                if ss.get("comboPick") != "yes":
                    b["searched_not_offered"] += 1
                if ss.get("missing") == want:
                    offered = ss.get("comboPick") == "yes"

            reasons: list[str] = []
            if loc != "Library":
                reasons.append("in_" + loc.lower())
            if restr is False:
                reasons.append("restriction")
            if tc["reach"] is not None:
                basis, unreachable = "shim", tc["reach"] is False
                if unreachable and not reasons:
                    reasons.append("shim_reach_false")
            elif offered is not None:
                basis, unreachable = "forge_offer", not offered
                if unreachable and not reasons:
                    reasons.append("not_offered")
            elif reasons:
                basis, unreachable = ("zones" if loc != "Library" else "index"), True
            elif restr is True or restr == COND:
                basis, unreachable = "index", False
            else:
                basis, unreachable = "unknown", False
            _inc(b, "reach_basis", basis)
            if unreachable:
                b["unreachable"] += 1
                for r in reasons:
                    _inc(b, "unreachable_reasons", r)
                why = []
                for r in reasons:
                    if r == "restriction":
                        why.append("its search is limited to " + " or ".join(cts))
                    elif r.startswith("in_"):
                        zone = {"command": "command zone"}.get(r[3:], r[3:])
                        why.append(f"it was already in the {zone}")
                    elif r == "not_offered":
                        why.append("Forge's search did not offer it")
                    elif r == "shim_reach_false":
                        why.append("the shim logged reach=false")
                self.flag(g.index, t, p, "tutor_unreachable",
                          f"{tutor} was cast seeking {want}, which it could not find: "
                          + "; ".join(why) + ".", ai)

            if attempt and attempt["status"] == "failed":
                b["failed_to_target"] += 1
                self.flag(g.index, t, p, "tutor_failed_target",
                          f"{tutor} could not be cast ({attempt['why']}); "
                          f"it was cast seeking {want}.", ai)
            elif attempt and attempt.get("x") is not None:
                b["x_resolved"] += 1
                if attempt["x"] == 0:
                    b["x_zero"] += 1
                    self.flag(g.index, t, p, "tutor_x_zero",
                              f"{tutor} resolved with X=0; it was cast seeking {want}.", ai)

            mode = self.reach.cast_mode(tutor)
            if mode in ("keyword", "activated"):
                _inc(b, "cast_never_searches", mode)
                self.flag(g.index, t, p, "tutor_cast_never_searches",
                          f"{tutor} was cast as a spell seeking {want}, but its search is "
                          f"{'a keyword' if mode == 'keyword' else 'an activated'} ability, "
                          "so casting it never searches.", ai)

    def _searches(self, g, scan: _GameScan) -> None:
        steers: dict[tuple, tuple[int, dict]] = {}
        for ai, a in enumerate(g.agent_events):
            if a.get("event") == "tutor_steer":
                s = parse_steer(a.get("detail"))
                if s:
                    steers[(a.get("player"), s["sid"])] = (ai, s)
        for ai, a in enumerate(g.agent_events):
            if a.get("event") != "search_seen":
                continue
            p, t = a.get("player"), a.get("turn")
            ss = parse_search_seen(a.get("detail"))
            b = self.bucket(g.index, p)
            st_ai, st = steers.get((p, ss.get("sid")), (None, None))
            picked = [x for x in (ss.get("picked") or "").split("|") if x and x != "-"]
            final = st["steer"] if st else (picked[0] if picked else None)
            src = ss.get("src") or "?"
            if ss.get("dest") == "Graveyard":
                b["gy_searches"] += 1
                if final:
                    b["gy_searches_picked"] += 1
                if st:
                    b["gy_steers"] += 1
                    use, why = self.graveyard_use(st["steer"], p, scan)
                    cls = "graveyard_use" if use else ("no_use" if use is False else "unknown")
                    b["gy_steers_" + cls] += 1
                    _inc(b, "gy_steer_cards", cls, st["steer"])
                    if use is False:
                        self.flag(g.index, t, p, "tutor_gy_steer_no_use",
                                  f"{src} put {st['steer']} into the graveyard over "
                                  f"{st['over']}; {st['steer']} has no use there.", st_ai)
            closers = self.closers(p)
            if any(x in closers for x in picked):
                b["closer_seen"] += 1
                if st and st["steer"] not in closers:
                    b["closer_overrides"] += 1
                    self.flag(g.index, t, p, "tutor_closer_override",
                              f"{src}: the plan took {st['steer']} over {st['over']}, "
                              "a proven closer.", st_ai)

    def _tutor_spells(self, g, scan: _GameScan) -> None:
        Z = scan.Z
        shim_casts: dict[tuple, int] = {}
        for a in g.agent_events:
            if a.get("event") == "tutor_cast":
                tc = parse_tutor_cast(a.get("detail"))
                if tc:
                    k = (a.get("player"), tc["tutor"], a.get("turn"))
                    shim_casts[k] = shim_casts.get(k, 0) + 1
        # Plan seats log every search they resolve: (player) -> [(ai, turn, parsed)]
        seen: dict[str, list] = {}
        steer_of: dict[tuple, str] = {}
        for ai, a in enumerate(g.agent_events):
            if a.get("event") == "search_seen":
                seen.setdefault(a.get("player"), []).append((ai, a.get("turn"),
                                                             parse_search_seen(a.get("detail"))))
            elif a.get("event") == "tutor_steer":
                s = parse_steer(a.get("detail"))
                if s:
                    steer_of[(a.get("player"), s["sid"])] = s["steer"]
        used_seen: set[int] = set()
        for zi, z in enumerate(Z):
            if z.get("token"):
                continue
            p = z.get("toPlayer") if z.get("to") == "Hand" else z.get("fromPlayer")
            if not p:
                continue
            tset = self.tutor_set(p, scan)
            if not tset or z.get("card") not in tset:
                continue
            b = self.bucket(g.index, p)
            if z.get("from") == "Library" and z.get("to") == "Hand":
                b["tutors_drawn"] += 1
                continue
            if not (z.get("from") == "Hand" and z.get("to") == "Stack"):
                continue
            card, t = z.get("card"), z.get("turn")
            b["tutor_spells_cast"] += 1
            k = (p, card, t)
            if shim_casts.get(k):
                shim_casts[k] -= 1
                b["tutor_spells_cast_by_shim"] += 1
            # A permanent (Imperial Recruiter, Birthing Pod) searches after it
            # resolves, under Forge's creature/permanent AI, not the tutor-spell
            # rule that holds library searches for main phase 2: its own kind.
            # A transmute or typecycling card cast as a spell does not search.
            fetch_kind = self.reach.dest_kind(card) or "unknown"
            f = self.reach.target_facts(card)
            if f and f["tokens"] & _PERMANENT:
                kind = "permanent"
            elif self.reach.cast_mode(card) == "keyword":
                kind = fetch_kind = "keyword_only"
            else:
                kind = fetch_kind
            ph = z.get("phase") or ""
            own = g.active.get(t) == p if t in g.active else None
            when = ("before_main2" if ph in PHASES_BEFORE_MAIN2 else
                    "main2_or_later" if ph in PHASES_MAIN2_OR_LATER else None)
            if own is None or when is None:
                bucket_name = "unknown"      # logs from before the shim stamped phase
            else:
                bucket_name = ("own_" if own else "opp_") + when
            _inc(b, "phase", kind, bucket_name)

            # What it fetched: the plan seat's own search record first.
            pick = None
            for ai, st_turn, ss in seen.get(p, []):
                if ai in used_seen or ss.get("src") != card:
                    continue
                if isinstance(st_turn, int) and isinstance(t, int) and 0 <= st_turn - t <= 1:
                    used_seen.add(ai)
                    pk = [x for x in (ss.get("picked") or "").split("|") if x and x != "-"]
                    pick = steer_of.get((p, ss.get("sid"))) or (pk[0] if pk else None)
                    break
            if fetch_kind == "keyword_only":
                continue
            fk = self._fetch_index(scan, zi, z, fetch_kind, p, pick)
            fetched_name = Z[fk].get("card") if fk is not None else pick
            if fetched_name:
                types = (Z[fk].get("types") if fk is not None else "") or \
                    self.ctx.facts.type_line(fetched_name)
                ptype = primary_type(types)
                _inc(b, "pick_types", ptype)
                if kind == "hand" and self.reach.generic(card):
                    b["generic_picks"] += 1
                    if ptype == "Creature":
                        b["generic_picks_creature"] += 1
            if kind in ("hand", "library_top") and fk is not None:
                _inc(b, "fetch_use", kind, "fetched")
                if self._used_same_turn(scan, fk, kind, t):
                    _inc(b, "fetch_use", kind, "used_same_turn")

    @staticmethod
    def _fetch_index(scan: _GameScan, zi: int, z: dict, kind: str, p: str, pick) -> int | None:
        Z = scan.Z
        cid, t = z.get("cardId"), z.get("turn")
        j = None
        for k in range(zi + 1, min(len(Z), zi + 400)):
            if Z[k].get("cardId") == cid and Z[k].get("from") == "Stack":
                j = k
                break
        lo, hi = zi + 1, (j if j is not None else min(len(Z), zi + 80))
        if j is not None and Z[j].get("to") == "Battlefield":
            hi = min(len(Z), j + 60)   # a permanent's ETB search comes after it lands
        dest = {"hand": "Hand", "library_top": "Library", "battlefield": "Battlefield",
                "graveyard": "Graveyard", "exile": "Exile"}.get(kind)
        for k in range(lo, hi):
            r = Z[k]
            if r.get("turn") != t or r.get("from") != "Library":
                continue
            if r.get("fromPlayer") != p and r.get("toPlayer") != p:
                continue
            if dest and r.get("to") != dest:
                continue
            if not dest and r.get("to") == "Library":
                continue
            if pick:
                if r.get("card") == pick:
                    return k
                continue
            return k
        return None

    @staticmethod
    def _used_same_turn(scan: _GameScan, fk: int, kind: str, turn) -> bool:
        Z = scan.Z
        cid = Z[fk].get("cardId")
        in_hand = kind == "hand"
        for m in range(fk + 1, len(Z)):
            r = Z[m]
            if r.get("turn") != turn:
                if isinstance(r.get("turn"), int) and isinstance(turn, int) and r["turn"] > turn:
                    break
                continue
            if r.get("cardId") != cid:
                continue
            if not in_hand and r.get("from") == "Library" and r.get("to") == "Hand":
                in_hand = True
                continue
            if in_hand and r.get("from") == "Hand" and r.get("to") in ("Stack", "Battlefield"):
                return True
            if r.get("from") == ("Hand" if in_hand else "Library"):
                return False
        return False

    # -- output -------------------------------------------------------------------

    def metrics(self) -> dict:
        pooled = new_bucket()
        by_pilot: dict[str, dict] = {}
        by_seat: dict[str, dict] = {}
        for (deck, pilot), b in sorted(self.buckets.items()):
            counts = _strip_ratios(b)
            _add(pooled, counts)
            _add(by_pilot.setdefault(pilot, new_bucket()), counts)
            by_seat.setdefault(deck, {})[pilot] = finalize(b)
        finalize(pooled)
        for b in by_pilot.values():
            finalize(b)
        basis = dict(self.ctx.basis())
        basis["reach_index"] = self.reach.available
        return {"detector": NAME, "kind": KIND, "basis": basis, "pooled": pooled,
                "by_pilot": by_pilot, "by_seat": by_seat}


def detect(ctx, reach: Reach | None = None) -> tuple[dict, list[dict]]:
    """(metrics, flags) for one run. See the module docstring."""
    d = _Detector(ctx, reach=reach)
    d.run()
    return d.metrics(), d.flags


# ---------------------------------------------------------------------- CLI --

def main(argv: list[str] | None = None) -> int:
    from qa import context as qctx
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="a result file, or raw shim JSONL")
    ap.add_argument("--plans", help="plans JSON (found next to the run when omitted)")
    ap.add_argument("--card-cache", help="card_cache.json to read (default engine's)")
    ap.add_argument("--forge-index", help="a built Forge index directory")
    ap.add_argument("--flags", action="store_true", help="print the flags too")
    ap.add_argument("--seats", action="store_true", help="print per-seat metrics")
    a = ap.parse_args(argv)
    facts = qctx.CardFacts.load(a.card_cache)
    forge = qctx.load_forge_index(a.forge_index)
    results, flags = [], []
    for p in a.paths:
        ctx = qctx.from_path(p, plans=a.plans, facts=facts, forge=forge)
        m, f = detect(ctx)
        results.append(m)
        flags += f
    out = results[0] if len(results) == 1 else combine(results)
    if not a.seats:
        out = {k: v for k, v in out.items() if k != "by_seat"}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    if a.flags:
        print(json.dumps(flags, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
