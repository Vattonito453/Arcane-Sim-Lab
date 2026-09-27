#!/usr/bin/env python3
"""Knockouts: who went out of each game, when, how, and to whom. Plus the
turning point: the turn the board swung hardest toward the eventual winner.

Repair plan WS1 task 1 (detector `knockouts`, rules-determined), WS11 task 1,
UX review section 2 problem 1 and section 4.6.

## Why the loss line cannot date a knockout

Forge prints every loser's "has lost" line at game end, in seat order. In game
1 of the playtester's run all four outcome lines sit at seqs 1012-1015 on the
final turn, so anything that dates a knockout by its loss line puts every
knockout on the last turn, and the scorecard's "median knockout round" was the
game length. The loss line is still the authority on the CAUSE (Forge wrote it,
and Forge adjudicated the game); it is only the moment that has to come from
elsewhere. Two things fix the moment, both read from the log, never inferred
from card text:

1. Forge's own turn sequence. An out player gets no more turns, so a knockout
   lies between the start of the player's last own turn and the first turn at
   which the table wrapped past their seat without them (the "window").
2. The last logged event of the loss's cause against that player inside the
   window: the Life line that took them to 0 or below, the last poison
   counters, the commander hit that crossed 21, the draw from an empty
   library, the resolution of the spell that won or made them lose.

Causes (`cause`):
    combat_damage     life reached 0; the lethal Life line followed combat damage
    noncombat_damage  life reached 0; it followed non-combat damage (burn, fight)
    life_loss         life reached 0 with no damage logged: a drain or paid life
    life_total        life reached 0 but no lethal Life line was logged (rare)
    poison            ten or more poison counters
    commander_damage  21 combat damage from one commander
    alt_win           an opponent won by a spell ("won by spell 'X'")
    lose_effect       a card's own "you lose the game" clause (an unpaid Pact)
    deckout           drew from an empty library
    concession        conceded
    unknown           a loss line this module does not recognise

## Attribution (`by`, `basis`)

`by` is the player whose card dealt the knockout. On shim runs it is the
controller of the source card by Forge card id, read from the zone stream
(`basis: "zones"`): the last move that put that id onto the battlefield or the
stack. A control change without a zone move (Threaten) is invisible there, so
`by` is the card's controller as of its last zone move. Where the zone stream
cannot answer, or on stock stdout runs, it comes from the log (`basis: "log"`):
the attack declaration that named the card, the cast or activation line, the
stack line a triggered ability resolved from ("P triggered Blood Artist"; a
trigger's resolution line prints its text and tags the object that set it
off, not its source), or Forge's "receives N poison counters from P". A
deck-out, a concession and an unknown loss carry no `by`. A lose-the-game
effect dated by the loser's own stack line for the card (their Pact trigger)
carries the loser as `by`; one dated only by another player's line (a
"target player loses the game" card) carries that card's controller.

`dated_by` is "event" when an event of the cause dated the knockout, and
"turn_order" when none was found and only the turn sequence bounds it (the
latest turn it can have happened on is used, and a flag is raised).

## Rounds

`round` is the table round of the knockout's turn: a player's Nth turn is
round N, counted with scorecard.true_round, the one Python copy of that rule
(the most turns any seat has taken up to and including that turn). At the
game's final knockout this is almost always the winner's own-turn count, the
unit the repair plan (section 2.1) measures win speed in, and it is the same
figure the scorecard's win round uses. It is one more than the winner's count
when the last knockout lands on the turn of a seat that plays before the
winner in that round (a Pact trigger on the loser's own upkeep, say): 141 of
the 5,591 decided games with knockouts in the local corpus (2026-09-27).

## Turning point

The turn with the largest shift in board power toward the eventual winner.
Board power is creature count and total power per seat at the end of each
turn:
  - shim runs: read from the zone stream, which records every battlefield
    entry and exit with Forge's own card id, core types and P/T as of the move
    (`basis: "zones"`). P/T changes while a creature stays on the battlefield
    (counters, anthems cast later) are not re-read, so power is as of entry.
  - stdout runs: inferred from the log (`basis: "log"`, `inferred: true`):
    creature spells that resolve with their P/T, token bursts Forge narrates
    ("P creates ten 1/1 red Goblin creature tokens"), creatures sighted
    attacking or blocking, and Battlefield exits. Tokens made by a trigger
    whose text Forge does not narrate appear only once they act.
The shift is the change in the winner's share of the table's creature power,
smoothed as if every seat also had one 3-power creature so that a lone 2/2 on
turn 2 does not read as the biggest swing of the game. Seats already knocked
out are left out of both ends of a turn's comparison, so an elimination is
never itself counted as a swing. Two turns with the same shift are split by
mass exits (more creatures leaving the battlefield wins), then by the shift in
creature count. `event_hint` names what moved the most
creature power toward the winner on that turn (a spell or ability's
resolution, or "combat"), each creature entering or leaving being charged to
the resolution or combat damage Forge logged it with; `event_by` is whose
card it was. On a stdout run whose owners the log cannot tell, it is what
moved the most power at all.

Stdlib only. The card cache is consulted without fetching, and only on stdout
runs or pre-0.3.0 shim logs whose zone records carry no types or P/T.

CLI:
    py engine/qa/knockouts.py <result.json> [<result.json> ...]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ENGINE = Path(__file__).resolve().parent.parent
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

from scorecard import true_round  # noqa: E402

DETECTOR = "knockouts"
KIND = "rules"   # rules-determined (WS1): checked against Forge's own record

CAUSES = ("combat_damage", "noncombat_damage", "life_loss", "life_total",
          "poison", "commander_damage", "alt_win", "lose_effect", "deckout",
          "concession", "unknown")

# The smoothing prior of the turning point, in power per seat (see docstring).
SHARE_PRIOR = 3.0
COMMANDER_DAMAGE = 21

# Forge's phase lines, as printed after the player's possessive ("'s" or "'"
# for a name ending in s), mapped to the PhaseType names the zone stream uses.
_PHASES = (
    ("untap step", "UNTAP"),
    ("upkeep step", "UPKEEP"),
    ("draw step", "DRAW"),
    ("main phase, precombat", "MAIN1"),
    ("beginning of combat step", "COMBAT_BEGIN"),
    ("declare attackers step", "COMBAT_DECLARE_ATTACKERS"),
    ("declare blockers step", "COMBAT_DECLARE_BLOCKERS"),
    ("first strike damage step", "COMBAT_FIRST_STRIKE_DAMAGE"),
    ("combat damage step", "COMBAT_DAMAGE"),
    ("end of combat step", "COMBAT_END"),
    ("main phase, postcombat", "MAIN2"),
    ("end step", "END_OF_TURN"),
    ("cleanup step", "CLEANUP"),
)
_PHASE_ORDER = {code: i for i, (_, code) in enumerate(_PHASES)}

# "Hullbreaker Horror (46) deals 6 combat damage to Ai(4)-Krenko Goblins."
# "Rolling Earthquake (375) deals 2 non-combat damage to Ai(1)-Shelly Siona."
# "Phyrexian Beast Token (977) deals 2 damage (As -1/-1 Counters) to Goblin Token (1000)."
# "... deals 5 combat damage to Ai(4)-Krenko Goblins(as poison counters)."
_DMG = re.compile(r"^(?P<src>.+?) deals (?P<n>\d+) (?P<kind>combat |non-combat )?"
                  r"damage (?:\([^)]*\)\s*)?to (?P<tgt>.+?)\.?\s*$")
_POISON_SUFFIX = "(as poison counters)"
# "Name (123)" -> name, id
_NAME_ID = re.compile(r"^(?P<name>.*?)\s*\((?P<id>\d+)\)\s*$")
# A resolved spell or ability: "Ezuri's Predation (124) - For each creature ..."
_RESOLVE_HEAD = re.compile(r"^(?P<name>[^\[\]]+?) \((?P<id>\d+)\) -\s")
# "... [Card: Drown in the Loch (72), Activator: Ai(1)-Kess, Reanimator, ..."
_CARD_TAG = re.compile(r"\[(?:Card|Zone Changer): (?P<name>[^\[\]]+?) \((?P<id>\d+)\)")
# "Leonin Shikari - Creature 2 / 2" (a creature spell resolving, stdout)
# The whole line, anchored: a trigger's printed text can END in
# "[..., SpellAbility: Hyrax Tower Scout - Creature 3 / 3]", and an unanchored
# match read the entire ability text as a creature's name.
_RESOLVE_PT = re.compile(r"^(?P<name>[^\[\]()]+?)\s+-\s+Creature\s+(?P<p>\d+)\s*/\s*"
                         r"(?P<t>\d+)\s*$")
_ATTACK = re.compile(r"^(.+?)\s+assigned\s+(.+?)\s+to attack\s+(.+?)\.?$")
_BLOCK = re.compile(r"^(.+?)\s+assigned\s+(.+?)\s+to block\s+(.+?)\.?$")
# "Name (123)" pairs in an attacker list: split on each instance id, never on
# commas (CLAUDE.md: card names carry commas; board._refs is the same rule).
_REF = re.compile(r"([^()\[\]]+?)\s*\((\d+)\)")
_JOIN = re.compile(r"^[\s,;]*(?:and\s+)?")
_TOKEN_BURST = re.compile(
    r" creates (?P<n>\w+) (?P<p>\d+)/(?P<t>\d+) (?P<desc>.+?) creature tokens?\b")
# The same, as a trigger's printed text ("... create a 1/1 blue Bird Illusion
# creature token with flying."). Used only on shim runs, where the zone stream
# caps the count at the tokens that really entered.
_TOKEN_TEXT = re.compile(
    r"\bcreate (?P<n>\w+) (?P<p>\d+)/(?P<t>\d+) (?P<desc>.+?) creature tokens?\b")
_WORDNUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
            "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "twenty": 20}
_COLOURS = {"white", "blue", "black", "red", "green", "colorless", "and"}
_DRAW_WORD = re.compile(r"\bdraws?\b", re.I)
# Where Forge's trailing tags start ("[Card: ...", "[Zone Changer: ...",
# "[Phase: ..."). A bare " [" is not enough: precon deck names carry brackets
# of their own ("Ai(2)-Squirreled Away [BLC] [2024]").
_TAGS = re.compile(r"\s\[[A-Z][A-Za-z ]*: ")
_YOU_DRAW = re.compile(r"\byou (?:may )?draws?\b")
# Trigger text in which someone other than the trigger's controller draws.
_OTHER_DRAWS = re.compile(
    r"\b(?:that player|target player|target opponent|each opponent|an opponent|"
    r"its controller|its owner|defending player|each other player)"
    r"(?: may)? draws?\b")
_QUOTED = re.compile(r"'(.+)'")


# ---------------------------------------------------------------------------
# One pass over the log
# ---------------------------------------------------------------------------

class _Ev:
    """One logged event with its place in the game, parsed once."""
    __slots__ = ("idx", "ti", "turn", "active", "phase", "seq", "action", "raw",
                 "dmg", "life", "recv")

    def __init__(self, idx, ti, turn, active, phase, e):
        self.idx = idx
        self.ti = ti
        self.turn = turn
        self.active = active
        self.phase = phase
        self.seq = e.get("seq")
        self.action = e.get("action") or ""
        self.raw = (e.get("raw") or "").strip()
        self.dmg = None    # (src_name, src_id, amount, kind, target, poison)
        self.life = None   # (player, before, after)
        self.recv = None   # (player, amount, from_player)


_OUTCOME_WHO = re.compile(r"^(.+?) has (?:lost|won)\b")


def _players_longest_first(game: dict) -> list[str]:
    players = list(game.get("players") or [])
    for t in game.get("turns") or []:
        ap = t.get("active_player")
        if ap and ap not in players:
            players.append(ap)
        # The outcome lines name every seat in full. Result files from the
        # adapter's first days (2026-07-22) truncated the player keys to
        # "Ai(1", so the names Forge printed are taken from these lines too.
        for e in t.get("events") or []:
            if e.get("action") == "game_outcome":
                m = _OUTCOME_WHO.match(e.get("raw") or "")
                if m and m.group(1) not in players:
                    players.append(m.group(1))
    return sorted(players, key=len, reverse=True)


def _player_at(text: str, players: list[str]) -> str | None:
    """The player key `text` starts with, longest first, at a word boundary.

    Player keys carry spaces, commas and apostrophes ("Ai(1)-Kess, Reanimator",
    "Ai(2)-Skrat's Revenge"), so they are matched against the known keys, never
    split out with a regex."""
    for p in players:
        if text.startswith(p) and (len(text) == len(p)
                                   or not text[len(p)].isalnum()):
            return p
    return None


def _phase_code(raw: str) -> str | None:
    low = raw.lower()
    for suffix, code in _PHASES:
        if low.endswith(suffix):
            return code
    return None


def _split_ref(text: str) -> tuple[str, str | None]:
    m = _NAME_ID.match(text.strip())
    if m:
        return m.group("name").strip(), m.group("id")
    return text.strip(), None


def _flatten(game: dict, players: list[str]) -> list[_Ev]:
    out: list[_Ev] = []
    for ti, t in enumerate(game.get("turns") or []):
        phase = ""
        active = t.get("active_player") or ""
        for e in t.get("events") or []:
            ev = _Ev(len(out), ti, t.get("turn", 0), active, phase, e)
            if ev.action == "phase":
                phase = _phase_code(ev.raw) or phase
                ev.phase = phase
            elif ev.action == "damage":
                m = _DMG.match(ev.raw)
                if m:
                    tgt = m.group("tgt").strip()
                    poison = tgt.lower().endswith(_POISON_SUFFIX)
                    if poison:
                        tgt = tgt[:-len(_POISON_SUFFIX)].strip()
                    name, cid = _split_ref(m.group("src"))
                    kind = "combat" if m.group("kind") == "combat " else "noncombat"
                    ev.dmg = (name, cid, int(m.group("n")), kind, tgt, poison)
                else:
                    who = _player_at(ev.raw, players)
                    if who and " poison counter" in ev.raw:
                        # "Ai(4)-Krenko Goblins receives 46 poison counter from
                        #  Ai(2)-Skrat's Revenge"
                        rest = ev.raw[len(who):]
                        mm = re.match(r"\s+receives\s+(\d+)\s+poison counters?"
                                      r"(?:\s+from\s+(.+?))?\.?\s*$", rest)
                        if mm:
                            src = _player_at(mm.group(2) or "", players)
                            ev.recv = (who, int(mm.group(1)), src)
            elif ev.action == "life_change" and ev.raw.startswith("Life:"):
                body = ev.raw[len("Life:"):].strip()
                who = _player_at(body, players)
                if who:
                    mm = re.match(r"\s*(-?\d+)\s*>\s*(-?\d+)\s*$", body[len(who):])
                    if mm:
                        ev.life = (who, int(mm.group(1)), int(mm.group(2)))
            out.append(ev)
    return out


# ---------------------------------------------------------------------------
# Who controlled a card
# ---------------------------------------------------------------------------

class _Zones:
    """Card-id controller lookups from the shim zone stream."""

    def __init__(self, game: dict):
        self.present = bool(game.get("zones"))
        self.moves: dict[str, list[tuple[int, str]]] = defaultdict(list)
        self.commanders: set[str] = set()
        self.library_moves: dict[str, list[dict]] = defaultdict(list)
        for rec in game.get("zones") or []:
            cid = rec.get("cardId")
            cid = None if cid in (None, -1) else str(cid)
            to, frm = rec.get("to"), rec.get("from")
            if cid and "Command" in (to, frm):
                self.commanders.add(cid)
            if frm == "Library" and rec.get("fromPlayer"):
                self.library_moves[rec["fromPlayer"]].append(rec)
            if not cid:
                continue
            if to == "Battlefield":
                ctl = rec.get("toPlayer") or rec.get("fromPlayer")
            elif to == "Stack":
                ctl = rec.get("fromPlayer") or rec.get("toPlayer")
            else:
                continue
            if ctl:
                self.moves[cid].append((rec.get("turn", 0), ctl))

    def controller(self, card_id: str | None, turn: int) -> str | None:
        if not card_id:
            return None
        best = None
        for t, ctl in self.moves.get(card_id, ()):
            if t > turn:
                break
            best = ctl
        return best


class _LogOwners:
    """Who a card belonged to, from the log alone: attack and block
    declarations, cast / activate / trigger lines, and Activator tags. Each
    observation is (event index, card id or None, lower-case name, player)."""

    def __init__(self, flat: list[_Ev], players: list[str]):
        self.obs: list[tuple[int, str | None, str, str]] = []
        for ev in flat:
            raw = ev.raw
            if ev.action == "combat":
                m = _ATTACK.match(raw) or _BLOCK.match(raw)
                if m:
                    who = _player_at(m.group(1), players)
                    if who:
                        for nm, cid in _refs(m.group(2)):
                            self.obs.append((ev.idx, cid, nm.lower(), who))
            elif ev.action == "stack_add":
                who = _player_at(raw, players)
                if who:
                    mm = re.match(r"\s+(?:cast|activated|triggered)\s+(.+?)"
                                  r"(?:\s+targeting\b.*)?$", raw[len(who):])
                    if mm:
                        nm, cid = _split_ref(mm.group(1))
                        self.obs.append((ev.idx, cid, nm.lower(), who))
            elif ev.action == "stack_resolve":
                i = raw.find("Activator: ")
                tag = _CARD_TAG.search(raw)
                if i >= 0 and tag:
                    who = _player_at(raw[i + len("Activator: "):], players)
                    if who:
                        self.obs.append((ev.idx, tag.group("id"),
                                         tag.group("name").strip().lower(), who))

    def controller(self, upto: int, card_id: str | None, name: str | None) -> str | None:
        low = (name or "").lower()
        for idx, cid, nm, who in reversed(self.obs):
            if idx > upto:
                continue
            if card_id and cid == card_id:
                return who
            if not card_id and low and nm == low:
                return who
        if card_id and low:
            # The id never appeared in a declaration: fall back to the name.
            for idx, cid, nm, who in reversed(self.obs):
                if idx <= upto and nm == low:
                    return who
        return None


def _refs(segment: str) -> list[tuple[str, str]]:
    return [(_JOIN.sub("", nm).strip(), cid) for nm, cid in _REF.findall(segment)]


class _Ctx:
    """Per-game lookups shared by knockouts() and turning_point()."""

    def __init__(self, game: dict):
        self.game = game
        self.turns = game.get("turns") or []
        self.players = _players_longest_first(game)
        self.flat = _flatten(game, self.players)
        self.zones = _Zones(game)
        self._owners: _LogOwners | None = None

    @property
    def owners(self) -> _LogOwners:
        if self._owners is None:
            self._owners = _LogOwners(self.flat, self.players)
        return self._owners

    def attribute(self, ev: _Ev, card: str | None, card_id: str | None
                  ) -> tuple[str | None, str | None]:
        """(by, basis) for the card that dealt a knockout at `ev`."""
        if self.zones.present and card_id:
            who = self.zones.controller(card_id, ev.turn)
            if who:
                return who, "zones"
        who = self.owners.controller(ev.idx, card_id, card)
        return (who, "log") if who else (None, None)

    def pairs(self, ti: int) -> dict[int, tuple[str, str, str | None]]:
        """{resolution event index: (player, card, id)} for turn index `ti`,
        pairing each "Resolve Stack" line with the "Add To Stack" line it
        resolves.

        A triggered ability resolves as its printed text ("Whenever Blood
        Artist or another creature dies, target player loses 1 life") with a
        tag naming the object that set it off, not its source; the source and
        its controller are on the stack line ("Ai(4)-Drana Vampires triggered
        Blood Artist"). Pairing is by name, most recent first, and only a
        text-only resolution may fall back to the top of the stack."""
        cache = self.__dict__.setdefault("_pairs", {})
        if ti in cache:
            return cache[ti]
        stack: list[tuple[str, str, str | None]] = []
        out: dict[int, tuple[str, str, str | None]] = {}
        for ev in self.flat:
            if ev.ti != ti:
                continue
            if ev.action == "stack_add":
                who = _player_at(ev.raw, self.players)
                if who:
                    mm = re.match(r"\s+(?:cast|activated|triggered)\s+(.+?)"
                                  r"(?:\s+targeting\b.*)?$", ev.raw[len(who):])
                    if mm:
                        name, cid = _split_ref(mm.group(1))
                        stack.append((who, name, cid))
            elif ev.action == "stack_resolve" and stack:
                headed = bool(_RESOLVE_HEAD.match(ev.raw) or _RESOLVE_PT.match(ev.raw))
                pick = next((j for j in range(len(stack) - 1, -1, -1)
                             if stack[j][1] and (ev.raw.startswith(stack[j][1])
                                                 or stack[j][1] in ev.raw)), None)
                if pick is None and not headed:
                    pick = len(stack) - 1
                if pick is not None:
                    out[ev.idx] = stack.pop(pick)
        cache[ti] = out
        return out

    def resolution_source(self, res: _Ev) -> tuple[str | None, str | None,
                                                   str | None, str | None]:
        """(card, id, controller, basis) of what a resolution line resolved."""
        head = _RESOLVE_HEAD.match(res.raw)
        pair = self.pairs(res.ti).get(res.idx)
        if head:
            card, cid = head.group("name").strip(), head.group("id")
            if self.zones.present:
                who = self.zones.controller(cid, res.turn)
                if who:
                    return card, cid, who, "zones"
            if pair and pair[1] == card:
                return card, cid, pair[0], "log"
            who = self.owners.controller(res.idx, cid, card)
            return card, cid, who, ("log" if who else None)
        pt = _RESOLVE_PT.match(res.raw)
        if pt:
            card = pt.group("name").strip()
            who = pair[0] if pair else self.owners.controller(res.idx, None, card)
            return card, None, who, ("log" if who else None)
        if pair:
            return pair[1], pair[2], pair[0], "log"
        tag = _CARD_TAG.search(res.raw)
        if tag:
            card, cid = tag.group("name").strip(), tag.group("id")
            by, basis = self.attribute(res, card, cid)
            return card, cid, by, basis
        return None, None, None, None


# ---------------------------------------------------------------------------
# Windows: when a player can have gone out, from Forge's turn order alone
# ---------------------------------------------------------------------------

def _turn_order(ctx: _Ctx) -> list[str]:
    order: list[str] = []
    for t in ctx.turns:
        ap = t.get("active_player")
        if ap and ap not in order:
            order.append(ap)
    for p in ctx.game.get("players") or []:
        if p not in order:
            order.append(p)
    return order


def _window(ctx: _Ctx, order: list[str], player: str) -> tuple[int, int]:
    """(first turn index, end turn index exclusive) the player went out in.

    From the start of their last own turn, walk the turns after it and track
    each active player's distance around the table from the player's seat.
    The distance only grows while the table works round to the player's seat;
    the first time it drops, the table has passed the seat without them, so
    they were out before that turn began. An extra turn repeats a distance and
    never drops it, so it does not close the window early."""
    turns = ctx.turns
    own = [i for i, t in enumerate(turns) if t.get("active_player") == player]
    if not own:
        return 0, len(turns)
    last = own[-1]
    pos = {p: i for i, p in enumerate(order)}
    n = len(order)
    prev = 0
    for j in range(last + 1, len(turns)):
        ap = turns[j].get("active_player")
        if ap not in pos or ap == player:
            continue
        d = (pos[ap] - pos[player]) % n
        if d < prev:
            return last, j
        prev = d
    return last, len(turns)


# ---------------------------------------------------------------------------
# Knockouts
# ---------------------------------------------------------------------------

def _reason_class(reason: str) -> str:
    r = reason.lower()
    if "life total reached" in r:
        return "life"
    if "poison" in r:
        return "poison"
    if "damage from general" in r or "commander damage" in r:
        return "commander_damage"
    if "empty library" in r or "draw cards from" in r or "tried to draw" in r:
        return "deckout"
    if "won by spell" in r:
        return "alt_win"
    if "effect of spell" in r or "due to effect of" in r:
        return "lose_effect"
    if "conced" in r:
        return "concession"
    return "unknown"


def _loss_lines(ctx: _Ctx) -> list[tuple[str, str, _Ev]]:
    """[(player, reason, outcome event)] for every seat that lost.

    Forge words a concession "X has conceded" rather than "X has lost ...",
    so it is read as a loss with the reason "conceded". None is logged in the
    local corpus (the AI does not concede); without this a conceding seat
    would get no knockout at all."""
    out = []
    seen = set()
    for ev in ctx.flat:
        if ev.action != "game_outcome":
            continue
        who = _player_at(ev.raw, ctx.players)
        if not who or who in seen:
            continue
        rest = ev.raw[len(who):].strip()
        if rest.startswith("has lost"):
            seen.add(who)
            out.append((who, rest[len("has lost"):].strip().rstrip("."), ev))
        elif rest.startswith("has conceded"):
            seen.add(who)
            out.append((who, "conceded", ev))
    return out


def _winner_spell(ctx: _Ctx) -> str | None:
    """"X has won due to effect of 'Thassa's Oracle'" -> the card."""
    for ev in ctx.flat:
        if ev.action == "game_outcome" and " has won " in ev.raw:
            m = _QUOTED.search(ev.raw)
            if m:
                return m.group(1)
    return None


def _in_window(ctx: _Ctx, lo: int, hi: int) -> list[_Ev]:
    return [ev for ev in ctx.flat if lo <= ev.ti < hi and ev.action != "game_outcome"]


def _resolve_source(ev: _Ev) -> tuple[str | None, str | None]:
    """(card, id) named by a resolution line."""
    m = _RESOLVE_HEAD.match(ev.raw)
    if m:
        return m.group("name").strip(), m.group("id")
    m = _CARD_TAG.search(ev.raw)
    if m:
        return m.group("name").strip(), m.group("id")
    return None, None


def _drain_source(ctx: _Ctx, lethal: _Ev) -> _Ev | None:
    """The resolution a damage-free life loss belongs to. Forge logs the Life
    line while the effect resolves and the "Resolve Stack" line after it, so
    look just after first, then just before, inside the same turn."""
    flat = ctx.flat
    for j in range(lethal.idx + 1, min(len(flat), lethal.idx + 6)):
        if flat[j].ti != lethal.ti:
            break
        if flat[j].action == "stack_resolve":
            return flat[j]
    for j in range(lethal.idx - 1, max(-1, lethal.idx - 6), -1):
        if flat[j].ti != lethal.ti:
            break
        if flat[j].action == "stack_resolve":
            return flat[j]
    return None


def _main_source(hits: list[_Ev]) -> _Ev:
    """The damage line of the source that dealt the most in `hits` (by card
    name, so nine Beast tokens outweigh the one Squirrel that connected
    last); on a tie, the later one."""
    total: dict[str, int] = defaultdict(int)
    last: dict[str, _Ev] = {}
    for ev in hits:
        total[ev.dmg[0]] += ev.dmg[2]
        last[ev.dmg[0]] = ev
    name = max(total, key=lambda n: (total[n], last[n].idx))
    return last[name]


def _life_knockout(ctx: _Ctx, player: str, evs: list[_Ev]) -> dict:
    lives = [ev for ev in evs if ev.life and ev.life[0] == player]
    downs = [ev for ev in lives if ev.life[2] < ev.life[1]]
    crossings = [ev for ev in downs if ev.life[1] > 0 >= ev.life[2]]
    lethal = crossings[-1] if crossings else (downs[-1] if downs else None)
    if lethal is None:
        # No Life line at all: the last damage to them is the best evidence.
        hits = [ev for ev in evs if ev.dmg and ev.dmg[4] == player and not ev.dmg[5]]
        if not hits:
            return {"cause": "life_total", "ev": None}
        last = hits[-1]
        cause = "combat_damage" if last.dmg[3] == "combat" else "noncombat_damage"
        return {"cause": cause, "ev": last, "card": last.dmg[0], "card_id": last.dmg[1]}

    # The damage that fed this Life line: damage to the player since their
    # previous life LOSS, in the same turn. A life gain in between (lifelink on
    # the same combat) does not split the group.
    prev = max((ev.idx for ev in downs if ev.idx < lethal.idx), default=-1)
    group = [ev for ev in ctx.flat[prev + 1:lethal.idx]
             if ev.ti == lethal.ti and ev.dmg and ev.dmg[4] == player
             and not ev.dmg[5]]
    if group:
        combat = sum(ev.dmg[2] for ev in group if ev.dmg[3] == "combat")
        other = sum(ev.dmg[2] for ev in group if ev.dmg[3] != "combat")
        kind = "combat" if combat and combat >= other else "noncombat"
        src = _main_source([ev for ev in group if ev.dmg[3] == kind])
        return {"cause": "combat_damage" if kind == "combat" else "noncombat_damage",
                "ev": lethal, "card": src.dmg[0], "card_id": src.dmg[1],
                "src_ev": src, "amount": lethal.life[1] - lethal.life[2]}
    res = _drain_source(ctx, lethal)
    out = {"cause": "life_loss", "ev": lethal, "card": None, "card_id": None,
           "amount": lethal.life[1] - lethal.life[2]}
    if res is not None:
        card, cid, by, basis = ctx.resolution_source(res)
        out.update(card=card, card_id=cid, src_ev=res)
        if by:
            out.update(by=by, by_basis=basis)
    return out


def _poison_knockout(ctx: _Ctx, player: str, evs: list[_Ev]) -> dict:
    hits = [ev for ev in evs
            if (ev.dmg and ev.dmg[5] and ev.dmg[4] == player)
            or (ev.recv and ev.recv[0] == player)]
    if not hits:
        return {"cause": "poison", "ev": None}
    last = hits[-1]
    dmg = ([ev for ev in hits if ev.dmg and ev.ti == last.ti]
           or [ev for ev in hits if ev.dmg])
    out = {"cause": "poison", "ev": last}
    if dmg:
        src = _main_source(dmg)
        out.update(card=src.dmg[0], card_id=src.dmg[1], src_ev=src)
    recv = [ev for ev in hits if ev.recv and ev.recv[2]]
    if recv:
        out["recv_from"] = recv[-1].recv[2]
    return out


def _commander_knockout(ctx: _Ctx, player: str, lo_idx: int, hi_idx: int) -> dict:
    """The combat hit that took one source's running total to the player past
    21. Commanders are known by id on shim runs (they move from the command
    zone); on stdout runs any source crossing 21 is a candidate and the last
    one in the window is taken."""
    totals: dict[str, int] = defaultdict(int)
    crossings: list[_Ev] = []
    last_hit = None
    for ev in ctx.flat[:hi_idx]:
        if not (ev.dmg and ev.dmg[3] == "combat" and ev.dmg[4] == player
                and not ev.dmg[5]):
            continue
        key = ev.dmg[1] or ev.dmg[0]
        before = totals[key]
        totals[key] += ev.dmg[2]
        if ev.idx >= lo_idx:
            last_hit = ev
            if before < COMMANDER_DAMAGE <= totals[key]:
                crossings.append(ev)
    known = [ev for ev in crossings if ev.dmg[1] in ctx.zones.commanders]
    pick = (known or crossings or [last_hit])[-1]
    if pick is None:
        return {"cause": "commander_damage", "ev": None}
    return {"cause": "commander_damage", "ev": pick, "card": pick.dmg[0],
            "card_id": pick.dmg[1]}


def _phase_key(turn: int, phase: str) -> tuple[int, int]:
    return turn, _PHASE_ORDER.get(phase or "", -1)


def _deckout_knockout(ctx: _Ctx, player: str, evs: list[_Ev]) -> dict:
    """The failed draw. Forge logs no draws, so the candidates are the
    player's own draw steps and any resolution that makes them draw. On shim
    runs the zone stream says when the last card left their library; the
    first candidate after that moment is the draw that could not happen."""
    def makes_them_draw(ev: _Ev) -> bool:
        if ev.action != "stack_resolve":
            return False
        # Forge's trailing tags ("[Card: X (1), Activator: P, ...]") name the
        # player who cast the spell that set a trigger off (Rhystic Study),
        # not who draws, so only the text before them is read.
        text = _TAGS.split(ev.raw, 1)[0]
        if not _DRAW_WORD.search(text):
            return False
        low = text.lower()
        if "each player draw" in low:
            return True
        if _RESOLVE_HEAD.match(ev.raw):
            # A spell or activated ability narrates who drew: "P draws a
            # card", "A, P and C each draw a card".
            for sentence in text.split(". "):
                i = sentence.find(player)
                if i >= 0 and _DRAW_WORD.search(sentence[i + len(player):]):
                    return True
            return False
        # A trigger prints its text instead ("..., draw a card", "you may
        # draw a card unless that player pays {1}"): the drawer is the
        # trigger's controller, from its stack line, unless the text hands
        # the draw to someone else.
        _card, _cid, by, _basis = ctx.resolution_source(ev)
        if by != player:
            return False
        # "Whenever an opponent draws their second card each turn, you draw
        # a card": an explicit "you draw" wins over any other drawer named.
        return bool(_YOU_DRAW.search(low)) or not _OTHER_DRAWS.search(low)

    cands = [ev for ev in evs
             if (ev.action == "phase" and ev.phase == "DRAW" and ev.active == player)
             or makes_them_draw(ev)]
    lib = ctx.zones.library_moves.get(player) or []
    out: dict = {"cause": "deckout", "ev": None}
    if lib:
        last = lib[-1]
        emptied = _phase_key(last.get("turn", 0), last.get("phase") or "")
        out["library_emptied"] = {"turn": last.get("turn", 0),
                                  "phase": last.get("phase") or ""}
        # The failed draw is the last draw logged for them at or after that
        # moment: once it happens they are out, so nothing of theirs follows.
        # (The first one after it can be the draw that took the last card:
        # zone records carry the phase, not an order within it.)
        later = [ev for ev in cands if _phase_key(ev.turn, ev.phase) >= emptied]
        if later:
            out.update(ev=later[-1], zones_dated=True)
            return out
        # Every candidate is from before the library emptied, so none of
        # them can be the failed draw: leave it to the turn order (flagged).
        return out
    if cands:
        out["ev"] = cands[-1]
    return out


def _named_event(ctx: _Ctx, evs: list[_Ev], card: str | None) -> _Ev | None:
    """The last event in `evs` that names `card`."""
    if not card:
        return None
    for ev in reversed(evs):
        if card in ev.raw and ev.action in ("stack_resolve", "stack_add",
                                            "zone_change", "life_change"):
            return ev
    return None


_STACK_VERB = re.compile(r"\s+(cast|activated|triggered)\s+(.+?)(?:\s+targeting\b.*)?$")


def _own_card_event(ctx: _Ctx, evs: list[_Ev], card: str | None,
                    player: str) -> tuple[_Ev | None, str | None]:
    """The last event in `evs` in which `player`'s own `card` went on or came
    off the stack: their stack line for it ("P triggered Pact of Negation",
    "P cast Final Fortune"; a card named only as a target does not count), or
    a resolution whose source is that card under their control.

    A lose-the-game clause on a Pact or a Final Fortune is the loser's own, so
    their own line dates it. Searching every player's lines instead picked up
    an opponent casting or triggering the same card later in the loser's
    window: on the local corpus 2 of 26 such knockouts were dated to an
    opponent's Pact of Negation, a turn or more late, with `by` naming that
    opponent.

    Returns (event, basis of the ownership read), or (None, None)."""
    if not card:
        return None, None
    for ev in reversed(evs):
        if card not in ev.raw:
            continue
        if ev.action == "stack_add":
            if _player_at(ev.raw, ctx.players) != player:
                continue
            m = _STACK_VERB.match(ev.raw[len(player):])
            if m and _split_ref(m.group(2))[0] == card:
                return ev, "log"
        elif ev.action == "stack_resolve":
            src, _cid, who, basis = ctx.resolution_source(ev)
            if src == card and who == player:
                return ev, basis or "log"
    return None, None


def knockouts(game: dict, _ctx: _Ctx | None = None) -> list[dict]:
    """Every player who went out of `game`, in the order they went out.

    [{player, turn, round, cause, by, card, seq, basis, dated_by, reason}]:
    player and by are raw player keys ("Ai(2)-Skrat's Revenge"; strip the
    seat prefix for display); turn is Forge's turn number, round the table
    round (see module docstring). A game with no loss lines (a draw, or an
    old log that recorded only the winner) returns [].
    """
    ctx = _ctx or _Ctx(game)
    losses = _loss_lines(ctx)
    if not losses:
        return []
    order = _turn_order(ctx)
    winner = (game.get("result") or {}).get("winner")
    out: list[dict] = []
    for loss_rank, (player, reason, loss_ev) in enumerate(losses):
        klass = _reason_class(reason)
        lo, hi = _window(ctx, order, player)
        evs = _in_window(ctx, lo, hi)
        found: dict
        if klass == "life":
            found = _life_knockout(ctx, player, evs)
        elif klass == "poison":
            found = _poison_knockout(ctx, player, evs)
        elif klass == "commander_damage":
            lo_idx = evs[0].idx if evs else 0
            hi_idx = (evs[-1].idx + 1) if evs else 0
            found = _commander_knockout(ctx, player, lo_idx, hi_idx)
        elif klass == "deckout":
            found = _deckout_knockout(ctx, player, evs)
        elif klass in ("alt_win", "lose_effect"):
            card = None
            m = _QUOTED.search(reason)
            if m:
                card = m.group(1)
            own_basis = None
            if klass == "alt_win":
                card = card or _winner_spell(ctx)
                # Every loser goes out at the same moment: the winning spell.
                allevs = [ev for ev in ctx.flat if ev.action != "game_outcome"]
                ev = _named_event(ctx, allevs, card)
            else:
                # The loser's own line for the card first (an unpaid Pact);
                # any player's line naming it only when there is none (a
                # "target player loses the game" effect cast by someone else).
                ev, own_basis = _own_card_event(ctx, evs, card, player)
                if ev is None:
                    ev = _named_event(ctx, evs, card)
            found = {"cause": klass, "ev": ev, "card": card, "card_id": None}
            if own_basis:
                found.update(by=player, by_basis=own_basis)
            if ev is not None:
                c2, cid = _resolve_source(ev)
                if c2 == card:
                    found["card_id"] = cid
        else:
            found = {"cause": klass, "ev": None}

        ev = found.get("ev")
        dated_by = "event"
        if ev is None:
            dated_by = "turn_order"
            ti = max(lo, hi - 1) if ctx.turns else 0
            turn_no = ctx.turns[ti].get("turn", 0) if ctx.turns else 0
            seq = None
            # Sorted after every event of the turn it is dated to, and before
            # any later turn's, so an undated knockout from early in a
            # multiplayer game can never become the game's final knockout
            # (and set its method) just for lacking an event.
            in_turn = [e.idx for e in ctx.flat if e.ti == ti and e.action != "game_outcome"]
            later = [e.idx for e in ctx.flat if e.ti > ti]
            key_idx = (max(in_turn) + 0.5 if in_turn
                       else (later[0] - 0.5 if later
                             else (ctx.flat[-1].idx + 1 if ctx.flat else 0)))
        else:
            ti, turn_no, seq, key_idx = ev.ti, ev.turn, ev.seq, ev.idx

        by, basis = found.get("by"), found.get("by_basis")
        card, card_id = found.get("card"), found.get("card_id")
        if by is None and ev is not None and found["cause"] in (
                "combat_damage", "noncombat_damage", "life_loss", "poison",
                "commander_damage", "lose_effect", "alt_win"):
            src_ev = found.get("src_ev") or ev
            by, basis = ctx.attribute(src_ev, card, card_id)
            if by is None and found.get("recv_from"):
                by, basis = found["recv_from"], "log"
            if by is None and found["cause"] == "alt_win" and winner:
                by, basis = winner, "log"
        if basis is None:
            basis = "zones" if (ctx.zones.present and found.get("zones_dated")) else "log"

        ko = {
            "player": player,
            "turn": turn_no,
            "round": true_round(game, ti) if ctx.turns else 0,
            "cause": found["cause"],
            "by": by,
            "card": card,
            "seq": seq,
            "basis": basis,
            "dated_by": dated_by,
            "reason": reason,
        }
        if found.get("amount") is not None:
            ko["amount"] = found["amount"]
        if found.get("library_emptied"):
            ko["library_emptied"] = found["library_emptied"]
        # The winner's spells earlier in the knockout's turn: the context a
        # reader needs for "poison (Triumph of the Hordes)", where Forge's
        # damage line names only the token that connected. Log facts only.
        if by and ev is not None:
            spells = [
                re.sub(r"\s+targeting\b.*$", "", e.raw[len(by):].strip()[len("cast"):]).strip()
                for e in ctx.flat
                if e.ti == ti and e.idx < ev.idx and e.action == "stack_add"
                and e.raw.startswith(by + " cast ")]
            if spells:
                ko["cast_before"] = spells
        ko["_order"] = (key_idx, loss_rank)
        ko["_ti"] = ti
        out.append(ko)
    out.sort(key=lambda k: k["_order"])
    for k in out:
        del k["_order"]
    return [_public(k) for k in out]


def _public(k: dict) -> dict:
    k = dict(k)
    k.pop("_ti", None)
    return k


# ---------------------------------------------------------------------------
# Board power per seat per turn
# ---------------------------------------------------------------------------

def _power_of(pt: str | None) -> int | None:
    if not pt or "/" not in pt:
        return None
    head = pt.split("/", 1)[0].strip()
    try:
        return int(head)
    except ValueError:
        return 0


def _printed(name: str) -> tuple[bool | None, int | None]:
    """(is creature, printed power) from the card cache, never fetching."""
    try:
        import cards  # noqa: PLC0415  lazy: the scorecards path must not need it
    except Exception:  # noqa: BLE001
        return None, None
    try:
        c = cards.get(name, fetch=False)
    except Exception:  # noqa: BLE001
        return None, None
    if not c:
        return None, None
    tl = c.get("type_line") or ""
    power = c.get("power")
    return ("Creature" in tl), (_power_of(f"{power}/0") if power is not None else None)


def _zone_board(ctx: _Ctx) -> list[dict[str, list[int]]]:
    """[{seat: [creatures, power]}] at the end of each turn index, read from
    the zone stream."""
    recs = ctx.game.get("zones") or []
    objs: dict[str, tuple[str, int]] = {}
    snaps: list[dict[str, list[int]]] = []
    ri = 0
    synth = 0
    for t in ctx.turns:
        tn = t.get("turn", 0)
        while ri < len(recs) and (recs[ri].get("turn", 0) or 0) <= tn:
            rec = recs[ri]
            ri += 1
            name = rec.get("card") or ""
            cid = rec.get("cardId")
            key = f"id{cid}" if cid not in (None, -1) else None
            if rec.get("to") == "Battlefield":
                types = rec.get("types") or ""
                power = _power_of(rec.get("pt"))
                if types:
                    creature = "Creature" in types.split(",")
                elif rec.get("token") and power is not None:
                    creature = True
                else:
                    creature, printed = _printed(name)
                    power = power if power is not None else printed
                if not creature:
                    if key:
                        objs.pop(key, None)
                    continue
                if key is None:
                    synth += 1
                    key = f"{name}#{synth}"
                owner = rec.get("toPlayer") or rec.get("fromPlayer") or ""
                objs[key] = (owner, power if power is not None else 1)
            elif rec.get("from") == "Battlefield":
                if key and key in objs:
                    del objs[key]
                elif key is None:
                    for k in [k for k in objs if k.startswith(name + "#")][:1]:
                        del objs[k]
        snap: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for owner, power in objs.values():
            snap[owner][0] += 1
            snap[owner][1] += max(0, power)
        snaps.append(dict(snap))
    return snaps


def _token_name(desc: str) -> str:
    words = [w for w in desc.split() if w.lower() not in _COLOURS]
    return (" ".join(words) + " Token").strip()


def _log_board(ctx: _Ctx) -> list[dict[str, list[int]]]:
    """[{seat: [creatures, power]}] per turn index, INFERRED from the stdout log.

    Entries: creature spells resolving with their P/T, narrated token bursts,
    creatures first sighted attacking or blocking. Exits: Battlefield exits,
    by instance id when the object was sighted with one, else by name."""
    players = ctx.players
    objs: dict[str, list] = {}         # key -> [owner, power, name, id]
    by_id: dict[str, str] = {}
    pending: dict[str, str] = {}
    synth = 0
    snaps: list[dict[str, list[int]]] = []

    def add(owner: str, name: str, power: int, cid: str | None) -> None:
        nonlocal synth
        synth += 1
        key = f"o{synth}"
        objs[key] = [owner, power, name.lower(), cid]
        if cid:
            by_id[cid] = key

    def sight(owner: str, name: str, cid: str) -> None:
        if cid in by_id:
            return
        low = name.lower()
        for key, o in objs.items():
            if o[3] is None and o[2] == low and o[0] == owner:
                o[3] = cid
                by_id[cid] = key
                return
        # Anything declared attacking or blocking is a creature right then,
        # whatever its printed type (a manland like Inkmoth Nexus).
        _creature, printed = (True, 1) if "token" in low else _printed(name)
        add(owner, name, printed if printed is not None else 1, cid)

    ti_prev = 0
    for ev in ctx.flat:
        while ev.ti > ti_prev:
            snaps.append(_snap(objs))
            ti_prev += 1
        raw = ev.raw
        if ev.action == "stack_add":
            who = _player_at(raw, players)
            if who:
                mm = re.match(r"\s+cast\s+(.+?)(?:\s+targeting\b.*)?$", raw[len(who):])
                if mm:
                    pending[_split_ref(mm.group(1))[0].lower()] = who
        elif ev.action == "stack_resolve":
            m = _RESOLVE_PT.match(raw)
            if m:
                owner = pending.pop(m.group("name").strip().lower(), None)
                if owner:
                    add(owner, m.group("name").strip(), int(m.group("p")), None)
                continue
            for p in players:
                i = raw.find(p + " creates ")
                if i < 0:
                    continue
                tb = _TOKEN_BURST.search(raw, i + len(p))
                if tb:
                    n = _WORDNUM.get(tb.group("n").lower())
                    if n is None and tb.group("n").isdigit():
                        n = int(tb.group("n"))
                    for _ in range(min(n or 1, 200)):
                        add(p, _token_name(tb.group("desc")), int(tb.group("p")), None)
                break
        elif ev.action == "combat":
            m = _ATTACK.match(raw) or _BLOCK.match(raw)
            if m:
                who = _player_at(m.group(1), players)
                if who:
                    for nm, cid in _refs(m.group(2)):
                        sight(who, nm, cid)
        elif ev.action == "zone_change" and "from Battlefield" in raw:
            mm = re.match(r"^(.+?)\s*\((\d+)\)\s+was put into\s+\w+\s+from\s+Battlefield", raw)
            if not mm:
                continue
            name, cid = mm.group(1).strip(), mm.group(2)
            key = by_id.pop(cid, None)
            if key and key in objs:
                del objs[key]
                continue
            low = name.lower()
            for k in reversed(list(objs)):
                if objs[k][3] is None and objs[k][2] == low:
                    del objs[k]
                    break
    while len(snaps) < len(ctx.turns):
        snaps.append(_snap(objs))
    return snaps


def _snap(objs: dict[str, list]) -> dict[str, list[int]]:
    snap: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for owner, power, _name, _cid in objs.values():
        snap[owner][0] += 1
        snap[owner][1] += max(0, power)
    return dict(snap)


def board_power(game: dict, _ctx: _Ctx | None = None) -> tuple[list[dict], str]:
    """([{seat: [creatures, power]}] per turn index, basis)."""
    ctx = _ctx or _Ctx(game)
    if ctx.zones.present:
        return _zone_board(ctx), "zones"
    return _log_board(ctx), "log"


# ---------------------------------------------------------------------------
# Turning point
# ---------------------------------------------------------------------------

def _share(snap: dict, seats: list[str], winner: str, prior: float) -> float:
    total = sum((snap.get(s) or [0, 0])[1] for s in seats)
    mine = (snap.get(winner) or [0, 0])[1]
    return (mine + prior) / (total + prior * len(seats)) if seats else 0.0


def _count_share(snap: dict, seats: list[str], winner: str) -> float:
    total = sum((snap.get(s) or [0, 0])[0] for s in seats)
    mine = (snap.get(winner) or [0, 0])[0]
    return (mine + 1) / (total + len(seats)) if seats else 0.0


def _exits_per_turn(ctx: _Ctx) -> list[int]:
    """Creatures that left the battlefield on each turn index: the turning
    point's tie-break (UX review problem 1: mass exits break a tie in board
    power). Shim runs read the zone records (typed since shim 0.3.0; an
    untyped record counts when it is a token with P/T or the card cache,
    never fetched, says creature). Stdout runs read Forge's "... from
    Battlefield" lines, which do not say what the card was: a token counts,
    and otherwise only a card the cache knows as a creature, the same rule
    the board inference charges exits by."""
    counts = [0] * len(ctx.turns)
    if ctx.zones.present:
        ti_of: dict[int, int] = {}
        for i, t in enumerate(ctx.turns):
            ti_of.setdefault(t.get("turn", 0), i)
        for rec in ctx.game.get("zones") or []:
            if rec.get("from") != "Battlefield":
                continue
            i = ti_of.get(rec.get("turn", 0) or 0)
            if i is None:
                continue
            types = rec.get("types") or ""
            if types:
                creature = "Creature" in types.split(",")
            elif rec.get("token") and _power_of(rec.get("pt")) is not None:
                creature = True
            else:
                creature = bool(_printed(rec.get("card") or "")[0])
            if creature:
                counts[i] += 1
        return counts
    for ev in ctx.flat:
        if ev.action == "zone_change" and "from Battlefield" in ev.raw:
            mm = re.match(r"^(.+?)\s*\((\d+)\)\s+was put into\s+\w+\s+from\s+Battlefield",
                          ev.raw)
            if not mm:
                continue
            name = mm.group(1).strip()
            if "token" in name.lower() or _printed(name)[0]:
                counts[ev.ti] += 1
    return counts


_COMBAT_DAMAGE_PHASES = ("COMBAT_FIRST_STRIKE_DAMAGE", "COMBAT_DAMAGE")


def _creature_table(ctx: _Ctx, turn_no: int) -> tuple[dict, dict]:
    """({card id: (owner, power)} for every creature that entered the
    battlefield up to the end of `turn_no`, {card id: (owner, power, name)}
    for those that entered ON it}), read from the zone stream. Power is as of
    entry. Both empty on stdout runs."""
    table: dict[str, tuple[str, int]] = {}
    entered: dict[str, tuple[str, int, str]] = {}
    for rec in ctx.game.get("zones") or []:
        t = rec.get("turn", 0) or 0
        if t > turn_no:
            break
        if rec.get("to") != "Battlefield":
            continue
        cid = rec.get("cardId")
        if cid in (None, -1):
            continue
        name = rec.get("card") or ""
        types = rec.get("types") or ""
        power = _power_of(rec.get("pt"))
        if types:
            creature = "Creature" in types.split(",")
        elif rec.get("token") and power is not None:
            creature = True
        else:
            creature, printed = _printed(name)
            power = power if power is not None else printed
        if not creature:
            continue
        owner = rec.get("toPlayer") or rec.get("fromPlayer") or ""
        power = max(0, power if power is not None else 1)
        table[str(cid)] = (owner, power)
        if t == turn_no:
            entered[str(cid)] = (owner, power, name)
    return table, entered


def _impact_groups(ctx: _Ctx, ti: int, winner: str, seats: list[str]
                   ) -> list[tuple[str, int | None, int, int, str | None]]:
    """[(hint, seq, toward_winner, moved, by)]: what moved the board on turn
    index `ti`, in creature power.

    Every creature entering or leaving the battlefield is charged to what
    caused it, by Forge's logging order: an effect's damage lines are written
    BEFORE its "Resolve Stack" line and the deaths it causes right after, so
    non-combat damage is charged to the next resolution and an exit to the
    resolution or damage it follows. Combat damage (to a player, or to a
    creature in a combat damage step from a creature declared in this turn's
    combat, which Forge logs without the word "combat") is charged to
    "combat". Entries are charged to the resolution that names them (by card
    id on shim runs, including tokens that fight as they are made), to a
    creature spell's own resolution, or to a narrated token burst.
    `toward_winner` signs each move: power the winner gains, or an opponent
    still in the game loses, counts for; the reverse counts against.

    Charging by the most recent cast line instead was wrong whenever
    responses interleaved: in game 3 of the playtester's run a copied Ezuri's
    Predation was charged to a Staff of Domination activated in between."""
    players = ctx.players
    evs = [ev for ev in ctx.flat if ev.ti == ti]
    turn_no = ctx.turns[ti].get("turn", 0)
    table, entered = _creature_table(ctx, turn_no) if ctx.zones.present else ({}, {})
    opp = {p for p in seats if p != winner}
    fighters: set[str] = set()
    casters: dict[str, str] = {}
    for ev in evs:
        if ev.action == "combat":
            m = _ATTACK.match(ev.raw) or _BLOCK.match(ev.raw)
            if m:
                fighters.update(cid for _, cid in _refs(m.group(2)))
        elif ev.action == "stack_add":
            who = _player_at(ev.raw, players)
            if who:
                mm = re.match(r"\s+cast\s+(.+?)(?:\s+targeting\b.*)?$", ev.raw[len(who):])
                if mm:
                    casters[_split_ref(mm.group(1))[0].lower()] = who

    groups: dict[str, list] = {}
    charged: set[str] = set()

    def sign(owner: str | None) -> int:
        return 1 if owner == winner else (-1 if owner in opp else 0)

    def charge(anchor, delta: int, moved: int) -> None:
        name, seq, by = anchor
        g = groups.setdefault(name, [name, seq, 0, 0, by])
        g[2] += delta
        g[3] += moved

    def enter_id(anchor, cid: str | None) -> None:
        if cid is None or cid in charged or cid not in entered:
            return
        charged.add(cid)
        owner, power, _name = entered[cid]
        charge(anchor, sign(owner) * power, power)

    def entered_named(name: str, owner: str | None, n: int) -> list[str]:
        return [c for c, (o, _p, nm) in entered.items()
                if c not in charged and nm == name and (owner is None or o == owner)][:n]

    def leave(anchor, cid: str, name: str, idx: int) -> None:
        if cid in table:
            owner, power = table[cid]
        elif ctx.zones.present:
            return                      # not a creature
        else:
            creature, printed = (True, 1) if "token" in name.lower() else _printed(name)
            if not creature:
                return
            owner = ctx.owners.controller(idx, cid, name)
            power = printed if printed is not None else 1
        charge(anchor, -sign(owner) * power, power)

    def resolution(ev: _Ev):
        name, cid, by, _basis = ctx.resolution_source(ev)
        name = name or "a resolving ability"
        if by is None:
            by = casters.get(name.lower())
        return (name, ev.seq, by)

    anchor = None
    for k, ev in enumerate(evs):
        raw = ev.raw
        if ev.dmg and _player_at(ev.dmg[4], players) is None:
            src_id = ev.dmg[1]
            if ev.dmg[3] == "combat" or (ev.phase in _COMBAT_DAMAGE_PHASES
                                         and src_id in fighters):
                anchor = ("combat", ev.seq, None)
                continue
            res = (next((e for e in evs[k + 1:] if e.action == "stack_resolve"), None)
                   or next((e for e in reversed(evs[:k]) if e.action == "stack_resolve"),
                           None))
            if res is None:
                continue
            anchor = resolution(res)
            for cid in (src_id, _split_ref(ev.dmg[4])[1]):
                enter_id(anchor, cid)
        elif ev.dmg:
            if ev.dmg[3] == "combat":
                anchor = ("combat", ev.seq, None)
        elif ev.action == "stack_resolve":
            anchor = resolution(ev)
            m = _RESOLVE_PT.match(raw)
            if m:
                name = m.group("name").strip()
                owner = casters.get(name.lower()) or anchor[2]
                ids = entered_named(name, owner, 1)
                if ids:
                    enter_id(anchor, ids[0])
                elif not ctx.zones.present and owner:
                    p = int(m.group("p"))
                    charge(anchor, sign(owner) * p, p)
            narrated = False
            for p in players:
                i = raw.find(p + " creates ")
                if i < 0:
                    continue
                tb = _TOKEN_BURST.search(raw, i + len(p))
                if tb:
                    narrated = True
                    w = tb.group("n").lower()
                    n = _WORDNUM.get(w, int(w) if w.isdigit() else 1)
                    if ctx.zones.present:
                        for c in entered_named(_token_name(tb.group("desc")), p, n):
                            enter_id(anchor, c)
                    else:
                        pw = n * int(tb.group("p"))
                        charge(anchor, sign(p) * pw, pw)
                break
            if not narrated and entered:
                # A trigger's own text ("create a 1/1 blue Bird Illusion
                # creature token") is printed instead of a narration. On shim
                # runs the zone stream says which token of that name entered
                # for the resolution's controller, so charge that one; the
                # count is capped by what actually entered.
                tm = _TOKEN_TEXT.search(raw)
                if tm and anchor[2]:
                    w = tm.group("n").lower()
                    n = _WORDNUM.get(w, int(w) if w.isdigit() else 1)
                    for c in entered_named(_token_name(tm.group("desc")), anchor[2], n):
                        enter_id(anchor, c)
            for cid in re.findall(r"\((\d+)\)", raw):
                enter_id(anchor, cid)
        elif ev.action == "zone_change" and "from Battlefield" in raw:
            mm = re.match(r"^(.+?)\s*\((\d+)\)\s+was put into\s+\w+\s+from\s+Battlefield",
                          raw)
            if mm and anchor is not None:
                leave(anchor, mm.group(2), mm.group(1).strip(), ev.idx)
        elif ev.action == "combat":
            anchor = ("combat", ev.seq, None)
    return [tuple(g) for g in groups.values()]


def turning_point(game: dict, kos: list[dict] | None = None,
                  _ctx: _Ctx | None = None) -> dict | None:
    """The turn with the largest shift in board power toward the winner.

    {turn, round, seat, shift, basis, inferred, event_hint, event_by,
     event_seq, share_before, share_after} or None (a draw, no winner, or no turn that
    moved the board toward the winner). `seat` is whose turn it was;
    share_before/after are the winner's raw share of the table's creature
    power among the seats compared (for prose: "from 15% to 86%").
    """
    res = game.get("result") or {}
    winner = res.get("winner")
    if not winner or res.get("draw"):
        return None
    ctx = _ctx or _Ctx(game)
    if not ctx.turns:
        return None
    kos = kos if kos is not None else knockouts(game, _ctx=ctx)
    # Turn index each loser went out on (the turn their knockout is dated to).
    out_at: dict[str, int] = {}
    tnum_to_ti: dict[int, int] = {}
    for i, t in enumerate(ctx.turns):
        tnum_to_ti.setdefault(t.get("turn", 0), i)
    for k in kos:
        out_at[k["player"]] = tnum_to_ti.get(k["turn"], len(ctx.turns))
    snaps, basis = board_power(game, _ctx=ctx)
    seats_all = [p for p in (game.get("players") or [])]
    if winner not in seats_all:
        seats_all.append(winner)

    best = None
    empty: dict = {}
    exits = _exits_per_turn(ctx)
    for i in range(len(snaps)):
        seats = [p for p in seats_all if p == winner or out_at.get(p, 10 ** 9) > i]
        before = snaps[i - 1] if i else empty
        after = snaps[i]
        shift = (_share(after, seats, winner, SHARE_PRIOR)
                 - _share(before, seats, winner, SHARE_PRIOR))
        if shift <= 0:
            continue
        cshift = _count_share(after, seats, winner) - _count_share(before, seats, winner)
        # A tie in the power shift goes to the turn more creatures left the
        # battlefield on (the UX review's tie-break), then to the larger
        # shift in creature count.
        key = (round(shift, 6), exits[i] if i < len(exits) else 0, round(cshift, 6))
        if best is None or key > best[0]:
            best = (key, i, seats, before, after, shift)
    if best is None:
        return None
    _, i, seats, before, after, shift = best

    def raw_share(snap):
        total = sum((snap.get(s) or [0, 0])[1] for s in seats)
        return round((snap.get(winner) or [0, 0])[1] / total, 3) if total else 0.0

    # The hint is what moved the most power toward the winner; on a stdout
    # run whose owners the log cannot tell, what moved the most power at all.
    groups = _impact_groups(ctx, i, winner, seats)
    hint = max(groups, key=lambda g: (g[2], g[3])) if groups else None
    if hint is not None and hint[2] <= 0:
        hint = max(groups, key=lambda g: g[3])
        if hint[3] <= 0:
            hint = None
    return {
        "turn": ctx.turns[i].get("turn", 0),
        "round": true_round(game, i),
        "seat": ctx.turns[i].get("active_player"),
        "shift": round(shift, 3),
        "basis": basis,
        "inferred": basis != "zones",
        "event_hint": hint[0] if hint else None,
        "event_by": hint[4] if hint else None,
        "event_seq": hint[1] if hint else None,
        "share_before": raw_share(before),
        "share_after": raw_share(after),
    }


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------

def analyse_game(game: dict) -> dict:
    """{"knockouts": [...], "turning_point": {...} | None} for one game,
    sharing one parse between the two."""
    ctx = _Ctx(game)
    kos = knockouts(game, _ctx=ctx)
    return {"knockouts": kos, "turning_point": turning_point(game, kos, _ctx=ctx)}


def _result_of(ctx) -> dict:
    if isinstance(ctx, dict):
        if "games" in ctx:
            return ctx
        return ctx.get("result") or {}
    return getattr(ctx, "result", None) or {}


def detect(ctx) -> tuple[dict, list[dict]]:
    """WS1 detector contract: (metrics, flags) for one run.

    `ctx` is the shared per-run context (a dict or object carrying `result`,
    the adapted result file); a bare result dict is accepted too.

    Flags are rules-determined facts worth a reviewer's look, each
    {detector, kind, game, turn, round, player, seq, detail}:
      undated_knockout   no event of the loss's cause was logged in the
                         player's window; dated by turn order only
      unclassified_loss  Forge's loss reason is not one this module knows
      deckout            the player lost drawing from an empty library
      analyzer_error     this module could not read the game (malformed
                         record); the game carries no knockouts and the rest
                         of the run is still read
    """
    result = _result_of(ctx)
    games = result.get("games") or []
    per_game = []
    by_cause: Counter = Counter()
    basis: Counter = Counter()
    flags: list[dict] = []
    tps = 0
    for n, game in enumerate(games, 1):
        try:
            one = analyse_game(game)
        except Exception as exc:  # noqa: BLE001  one bad game must not end the run
            per_game.append({"n": n, "knockouts": [], "turning_point": None,
                             "error": f"{type(exc).__name__}: {exc}"})
            flags.append({"detector": DETECTOR, "kind": "analyzer_error", "game": n,
                          "turn": None, "round": None, "player": None, "seq": None,
                          "detail": f"{type(exc).__name__}: {exc}"})
            continue
        per_game.append({"n": n, **one})
        if one["turning_point"]:
            tps += 1
        for k in one["knockouts"]:
            by_cause[k["cause"]] += 1
            basis[k["basis"]] += 1
            base = {"detector": DETECTOR, "game": n, "turn": k["turn"],
                    "round": k["round"], "player": k["player"], "seq": k["seq"]}
            if k["dated_by"] != "event":
                flags.append({**base, "kind": "undated_knockout",
                              "detail": f"no {k['cause']} event in the window; "
                                        f"dated by turn order ({k['reason']})"})
            if k["cause"] == "unknown":
                flags.append({**base, "kind": "unclassified_loss",
                              "detail": k["reason"]})
            if k["cause"] == "deckout":
                flags.append({**base, "kind": "deckout",
                              "detail": "lost drawing from an empty library"})
    metrics = {
        "games": len(games),
        "knockouts": sum(by_cause.values()),
        "by_cause": dict(by_cause),
        "basis": dict(basis),
        "undated": sum(1 for f in flags if f["kind"] == "undated_knockout"),
        "errors": sum(1 for f in flags if f["kind"] == "analyzer_error"),
        "turning_points": tps,
        "per_game": per_game,
    }
    return metrics, flags


def main(argv: list[str]) -> int:
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 1
    for p in paths:
        result = json.loads(Path(p).read_text(encoding="utf-8"))
        metrics, flags = detect(result)
        print(f"\n{Path(p).name}: {metrics['games']} games, "
              f"{metrics['knockouts']} knockouts {metrics['by_cause']}")
        for g in metrics["per_game"]:
            print(f"  game {g['n']}:")
            for k in g["knockouts"]:
                print(f"    round {k['round']:>2} (turn {k['turn']:>3}) "
                      f"{k['player']}: {k['cause']}"
                      + (f" by {k['by']}" if k["by"] else "")
                      + (f" with {k['card']}" if k["card"] else "")
                      + f" [seq {k['seq']}, {k['basis']}, {k['dated_by']}]")
            if g.get("error"):
                print(f"    not read: {g['error']}")
            tp = g["turning_point"]
            if tp:
                print(f"    turning point: round {tp['round']} (turn {tp['turn']}) "
                      f"{tp['seat']}, shift {tp['shift']} "
                      f"({tp['share_before']} -> {tp['share_after']}), "
                      f"{tp['event_hint']} [{tp['basis']}]")
        for f in flags:
            print(f"  FLAG {f['kind']}: game {f['game']} turn {f['turn']} "
                  f"{f['player']}: {f['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
