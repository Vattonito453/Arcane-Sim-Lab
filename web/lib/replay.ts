/** Event-folding engine for replays and run summaries. Pure functions only —
 *  no React, no fetch — so the whole thing is unit-testable against a result file.
 *
 *  Parsers are built from raw strings observed in real engine output
 *  (engine/sim_results/sim_*.json), e.g.:
 *    life_change   "Life: Ai(4)-Drana Vampires 18 > -69"          (explicit totals)
 *    land_drop     "Ai(1)-Kilo Helm Final played Mountain (88)"
 *    stack_add     "Ai(3)-Wyleth Voltron B3 cast Leonin Shikari"  (+ .object = name)
 *    stack_resolve "Leonin Shikari - Creature 2 / 2"              (creature spell)
 *                  "Sol Ring"                                     (noncreature permanent)
 *                  "Go for the Throat (155) - Destroy …"          (one-shot spell)
 *    zone_change   "Kilo, Apogee Mind (100) was put into Graveyard from Battlefield."
 *                  "Send countered spell to Graveyard"
 *    combat        "Ai(1)-… assigned Kilo, Apogee Mind (100) to attack Ai(4)-…"
 *    damage        "Zombie Token (477) deals 2 combat damage to Ai(4)-Drana Vampires."
 *                  "Ai(2)-… receives 1 poison counter from Ai(1)-…"
 *    game_outcome  "Ai(1)-… has lost because life total reached 0"
 *                  "Ai(2)-… has won because all opponents have lost"
 *    phase         "Ai(1)-Kilo Helm Final's Untap step" / "Ai(2)-Drana Vampires' Upkeep step"
 */

import type { SimEvent, SimGame } from "./types";
import { stripAi } from "./format";

/* ── public shapes ─────────────────────────────────────────────────────── */

export interface Card {
  name: string;
  tapped?: boolean;
  kinds?: string; // "land" | "creature" | "permanent" (best-effort)
  pt?: string; // "3/3" when the resolve raw carried power/toughness
}

export interface Seat {
  player: string; // full key, "Ai(1)-Kilo Helm Final"
  life: number;
  eliminated?: { turn: number } | null;
  poison?: number;
}

export interface BoardState {
  seats: Seat[];
  battlefield: Map<string, Card[]>;
  attacks: { from: string; to: string; cards: string[] } | null;
  stack: string[];
}

export interface Step {
  seq: number;
  turn: number; // player-turn number from the log; 0 = pregame
  phase: string; // phase label in effect at this step ("Untap step", "Pregame", …)
  active: string; // active player key ("" during pregame)
  text: string; // cleaned human-readable line (Ai(n)- prefixes and collector numbers removed)
  kind: string; // the event action
  delta?: number; // life delta for life_change steps
  hi?: string[]; // substrings of `text` worth bolding (card + player names)
  op?: Op; // internal fold instruction (exported for tests)
}

export interface Timeline {
  steps: Step[];
  players: string[];
  turns: { turn: number; start: number }[]; // first step index of each turn
  totalTurns: number;
}

export interface GameSummary {
  endedTurn: number;
  winner: string | null; // raw key
  winnerName: string | null; // stripped
  draw: boolean;
  durationMs: number;
  decidedBy: string; // short honest phrase from the last meaningful events
}

/* ── internal fold ops ─────────────────────────────────────────────────── */

export type Op =
  | { t: "life"; p: string; to: number }
  | { t: "poison"; p: string; n: number }
  | { t: "land"; p: string; name: string }
  | { t: "push"; p: string; name: string; verb: "cast" | "triggered" | "activated" }
  | { t: "resolve"; raw: string }
  | { t: "counterpop" }
  | { t: "leave"; name: string }
  | { t: "attack"; from: string; to: string; cards: string[] }
  | { t: "phase"; combat: boolean }
  | { t: "out"; p: string };

/* ── raw-string parsers ────────────────────────────────────────────────── */

const RE_AI = /Ai\(\d+\)-/g;
const RE_NUM = /\s\(\d+\)/g;
const RE_LIFE = /^Life: (.+?) (-?\d+) > (-?\d+)\s*$/;
const RE_POISON = /^(.+?) receives (\d+) poison counters? from /;
const RE_LAND = /^(.+?) played (.+?) \(\d+\)\s*$/;
const RE_STACK = /^(.+?) (cast|triggered|activated) (.+)$/;
// Forge batches a whole attacking squad onto ONE line:
//   "Ai(1)-X assigned Wilhelt, the Rotcleaver (200), Zombie Token (477) to attack Ai(4)-Y"
// so the middle group is a LIST and has to be split on the "(instance id)" that
// follows each name. Matching it as a single reference produced one bogus
// attacker named after the whole concatenated string. Mirrors _ATTACK/_REF in
// engine/board.py so the two stay in agreement.
const RE_ATTACK = /^(.+?) assigned (.+?) to attack (.+?)\.?\s*$/;
// Real form, from sim_results: "A (100), B (72) and C (326)". Splitting on the
// commas is not an option — card names contain them ("Kilo, Apogee Mind" and
// "Wilhelt, the Rotcleaver" both appear) — so each name is taken as everything
// up to its own "(instance id)", and only the joining punctuation is trimmed.
const RE_REF = /([^()]+?)\s*\((\d+)\)/g;
const RE_JOIN = /^[\s,;]*(?:and\s+)?/;

/** "A (1), B (2) and C (3)" → ["A", "B", "C"]. Whole string if it carries no ids. */
export function attackerNames(list: string): string[] {
  const out = Array.from(list.matchAll(RE_REF), (m) => m[1].replace(RE_JOIN, "").trim())
    .filter(Boolean);
  return out.length ? out : [list.replace(RE_NUM, "").trim()];
}
const RE_LEAVE = /^(.+?) \(\d+\) was put into \w+ from Battlefield\.?\s*$/;
const RE_DMG = /^(.+?) deals (\d+) (?:[\w-]+ )*damage(?:\s*\([^)]*\))? to (.+?)\.?\s*$/;
const RE_LOST = /^(.+?) has lost /;
const RE_WON = /^(.+?) has won /;

/** Strip Ai(n)- prefixes and collector numbers for display. */
export function cleanRaw(raw: string): string {
  return raw.replace(RE_AI, "").replace(RE_NUM, "");
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** "…'s Untap step" / "…' Upkeep step" → { p, label } */
function parsePhase(raw: string): { p: string; label: string } | null {
  const m = raw.match(/^(.+?)'s (.+)$/) || raw.match(/^(.+?)' (.+)$/);
  return m ? { p: m[1], label: m[2] } : null;
}

function prettyPhase(label: string): string {
  const s = label.trim();
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

const COMBAT_PHASES = [
  "beginning of combat",
  "declare attackers",
  "declare blockers",
  "first strike damage",
  "combat damage",
];
function isCombatPhase(label: string): boolean {
  const l = label.toLowerCase();
  return COMBAT_PHASES.some((c) => l.startsWith(c));
}

/** Damage raw → source card, amount, target (may be a player key or a creature). */
function parseDamage(raw: string): { source: string; amount: number; target: string } | null {
  const m = raw.match(RE_DMG);
  if (!m) return null;
  const source = m[1].replace(RE_NUM, "");
  let target = m[3].replace(/\(as poison counters\)$/, "").trim();
  target = target.replace(RE_NUM, "");
  return { source, amount: Number(m[2]), target };
}

/* ── timeline ──────────────────────────────────────────────────────────── */

function stepFor(ev: SimEvent, turn: number, active: string, phase: string): Step {
  const raw = ev.raw;
  const step: Step = {
    seq: ev.seq,
    turn,
    phase,
    active,
    text: cleanRaw(raw),
    kind: ev.action,
  };
  let m: RegExpMatchArray | null;

  switch (ev.action) {
    case "life_change":
      if ((m = raw.match(RE_LIFE))) {
        step.op = { t: "life", p: m[1], to: Number(m[3]) };
        step.delta = Number(m[3]) - Number(m[2]);
        step.hi = [stripAi(m[1])];
      }
      break;
    case "damage": {
      if ((m = raw.match(RE_POISON))) {
        step.op = { t: "poison", p: m[1], n: Number(m[2]) };
        step.hi = [stripAi(m[1])];
        break;
      }
      const d = parseDamage(raw);
      if (d) step.hi = [d.source, stripAi(d.target)];
      break;
    }
    case "land_drop":
      if ((m = raw.match(RE_LAND))) {
        step.op = { t: "land", p: m[1], name: m[2] };
        step.hi = [m[2], stripAi(m[1])];
      }
      break;
    case "stack_add":
      if ((m = raw.match(RE_STACK))) {
        const name = ev.object || m[3].replace(/ targeting \[.*$/, "").trim();
        step.op = { t: "push", p: m[1], name, verb: m[2] as "cast" | "triggered" | "activated" };
        step.hi = [name, stripAi(m[1])];
      }
      break;
    case "stack_resolve":
      step.op = { t: "resolve", raw };
      break;
    case "zone_change":
      if ((m = raw.match(RE_LEAVE))) {
        step.op = { t: "leave", name: m[1] };
        step.hi = [m[1]];
      } else if (raw.startsWith("Send countered spell")) {
        step.op = { t: "counterpop" };
      }
      break;
    case "combat":
      if ((m = raw.match(RE_ATTACK))) {
        const cards = attackerNames(m[2]);
        step.op = { t: "attack", from: m[1], to: m[3], cards };
        step.hi = [...cards, stripAi(m[3])];
      }
      break;
    case "phase": {
      const p = parsePhase(raw);
      if (p) {
        step.phase = prettyPhase(p.label);
        step.op = { t: "phase", combat: isCombatPhase(p.label) };
      }
      break;
    }
    case "game_outcome":
      if ((m = raw.match(RE_LOST))) {
        step.op = { t: "out", p: m[1] };
        step.hi = [stripAi(m[1])];
      } else if ((m = raw.match(RE_WON))) {
        step.hi = [stripAi(m[1])];
      }
      break;
    case "discard":
      if ((m = raw.match(/^(.+?) discards (.+?)(?: \(\d+\))?\.?\s*$/))) {
        step.hi = [m[2], stripAi(m[1])];
      }
      break;
    default:
      break;
  }
  return step;
}

/** One Step per event (pregame first), each with a cleaned display text. */
export function buildTimeline(game: SimGame): Timeline {
  const steps: Step[] = [];
  const turns: { turn: number; start: number }[] = [];
  let phase = "Pregame";

  for (const ev of game.events_pregame ?? []) {
    steps.push(stepFor(ev, 0, "", phase));
  }
  for (const t of game.turns) {
    turns.push({ turn: t.turn, start: steps.length });
    for (const ev of t.events) {
      const step = stepFor(ev, t.turn, t.active_player, phase);
      steps.push(step);
      phase = step.phase; // phase events update it; others inherit
    }
  }
  return {
    steps,
    players: game.players,
    turns,
    totalTurns: game.turns.length ? game.turns[game.turns.length - 1].turn : 0,
  };
}

/* ── folding ───────────────────────────────────────────────────────────── */

interface Pending {
  name: string;
  caster: string;
  verb: "cast" | "triggered" | "activated";
}

/** Classify a resolve raw for a cast card: battlefield permanent or one-shot spell. */
function resolveShape(raw: string, name: string): { board: boolean; kinds?: string; pt?: string } {
  const n = escapeRe(name);
  let m = raw.match(new RegExp(`^${n}(?: \\(\\d+\\))? - Creature (\\d+) / (\\d+)`));
  if (m) return { board: true, kinds: "creature", pt: `${m[1]}/${m[2]}` };
  if (new RegExp(`^${n}(?: \\(\\d+\\))?\\s*$`).test(raw)) return { board: true, kinds: "permanent" };
  m = raw.match(new RegExp(`^${n}(?: \\(\\d+\\))? - (Legendary |Artifact|Enchantment|Planeswalker|Battle|Kindred|Land)`));
  if (m) return { board: true, kinds: "permanent" };
  return { board: false }; // instant/sorcery effect text — not a permanent
}

/** Fold steps 0..i (inclusive) into a board state. Best-effort by design:
 *  the event feed stays the authoritative record. */
export function foldTo(timeline: Timeline, i: number): BoardState {
  const seats: Seat[] = timeline.players.map((p) => ({
    player: p,
    life: 40, // Commander
    eliminated: null,
    poison: 0,
  }));
  const byName = new Map(seats.map((s) => [s.player, s]));
  const battlefield = new Map<string, Card[]>(timeline.players.map((p) => [p, []]));
  const pending: Pending[] = [];
  let attacks: BoardState["attacks"] = null;

  const last = Math.min(i, timeline.steps.length - 1);
  for (let k = 0; k <= last; k++) {
    const step = timeline.steps[k];
    const op = step.op;
    if (!op) continue;
    switch (op.t) {
      case "life": {
        const s = byName.get(op.p);
        if (s) {
          s.life = op.to;
          if (op.to <= 0 && !s.eliminated) s.eliminated = { turn: step.turn };
        }
        break;
      }
      case "poison": {
        const s = byName.get(op.p);
        if (s) s.poison = (s.poison ?? 0) + op.n;
        break;
      }
      case "out": {
        const s = byName.get(op.p);
        if (s && !s.eliminated) s.eliminated = { turn: step.turn };
        break;
      }
      case "land": {
        battlefield.get(op.p)?.push({ name: op.name, kinds: "land" });
        break;
      }
      case "push":
        pending.push({ name: op.name, caster: op.p, verb: op.verb });
        break;
      case "resolve": {
        // Prefer the topmost pending item whose name the resolve raw names; else LIFO.
        let idx = -1;
        for (let j = pending.length - 1; j >= 0; j--) {
          if (op.raw.startsWith(pending[j].name)) {
            idx = j;
            break;
          }
        }
        const matched = idx >= 0;
        if (!matched) idx = pending.length - 1;
        if (idx < 0) break;
        const item = pending.splice(idx, 1)[0];
        if (matched && item.verb === "cast") {
          const shape = resolveShape(op.raw, item.name);
          if (shape.board) {
            battlefield.get(item.caster)?.push({ name: item.name, kinds: shape.kinds, pt: shape.pt });
          }
        }
        break;
      }
      case "counterpop":
        pending.pop();
        break;
      case "leave": {
        for (const cards of battlefield.values()) {
          const j = cards.findIndex((c) => c.name === op.name);
          if (j >= 0) {
            cards.splice(j, 1);
            break;
          }
        }
        break;
      }
      case "attack":
        if (attacks && attacks.from === op.from) {
          attacks.cards.push(...op.cards);
          attacks.to = op.to;
        } else {
          attacks = { from: op.from, to: op.to, cards: [...op.cards] };
        }
        break;
      case "phase":
        if (!op.combat) attacks = null;
        break;
    }
  }
  return { seats, battlefield, attacks, stack: pending.map((p) => p.name) };
}

/* ── game summary (results table + ledes) ──────────────────────────────── */

type LossKind = "life" | "commander" | "poison" | "other";

function lossKind(raw: string): LossKind {
  if (raw.includes("damage from generals")) return "commander";
  if (raw.includes("poison counters")) return "poison";
  if (raw.includes("life total reached")) return "life";
  return "other";
}

/** Short "decided by" text derived from the last meaningful events of a game. */
export function summarizeGame(game: SimGame): GameSummary {
  const flat: { turn: number; e: SimEvent }[] = [];
  for (const t of game.turns) for (const e of t.events) flat.push({ turn: t.turn, e });

  const endedTurn = game.turns.length ? game.turns[game.turns.length - 1].turn : 0;
  const winner = game.result.winner;
  const base: GameSummary = {
    endedTurn,
    winner,
    winnerName: winner ? stripAi(winner) : null,
    draw: game.result.draw,
    durationMs: game.result.duration_ms,
    decidedBy: game.result.draw ? "Draw" : "–",
  };
  if (game.result.draw) return base;

  // Final elimination = last "has lost" outcome in the log.
  let finalLoss: { raw: string; p: string; kind: LossKind } | null = null;
  for (const { e } of flat) {
    if (e.action === "game_outcome") {
      const m = e.raw.match(RE_LOST);
      if (m) finalLoss = { raw: e.raw, p: m[1], kind: lossKind(e.raw) };
    }
  }

  // Last life_change that took someone to 0 or below.
  let lethal: { idx: number; turn: number; p: string; delta: number } | null = null;
  for (let i = flat.length - 1; i >= 0; i--) {
    const { e, turn } = flat[i];
    if (e.action !== "life_change") continue;
    const m = e.raw.match(RE_LIFE);
    if (m && Number(m[3]) <= 0) {
      lethal = { idx: i, turn, p: m[1], delta: Number(m[2]) - Number(m[3]) };
      break;
    }
  }

  /** Dominant damage source hitting `victim` during turn `turn`, up to index `end`. */
  const dominantSource = (victim: string, turn: number, end: number) => {
    const totals = new Map<string, { sum: number; count: number }>();
    for (let i = end - 1; i >= 0; i--) {
      if (flat[i].turn !== turn) break;
      const e = flat[i].e;
      if (e.action !== "damage") continue;
      const d = parseDamage(e.raw);
      if (!d || (d.target !== victim && d.target !== stripAi(victim))) continue;
      const cur = totals.get(d.source) ?? { sum: 0, count: 0 };
      cur.sum += d.amount;
      cur.count += 1;
      totals.set(d.source, cur);
    }
    let best: { source: string; sum: number; count: number } | null = null;
    for (const [source, v] of totals) {
      if (!best || v.sum > best.sum) best = { source, ...v };
    }
    return best;
  };

  const kind = finalLoss?.kind ?? "life";
  if (kind === "poison") {
    const victim = finalLoss ? finalLoss.p : "";
    // Source card of "(as poison counters)" damage, if any.
    let src: string | null = null;
    for (let i = flat.length - 1; i >= 0; i--) {
      const e = flat[i].e;
      if (e.action === "damage" && e.raw.includes("as poison counters") && e.raw.includes(victim)) {
        src = parseDamage(e.raw)?.source ?? null;
        break;
      }
    }
    base.decidedBy = src ? `Poison from ${src}` : "Poison";
    return base;
  }
  if (kind === "commander") {
    const victim = finalLoss ? finalLoss.p : "";
    let src: string | null = null;
    if (lethal || victim) {
      for (let i = flat.length - 1; i >= 0; i--) {
        const e = flat[i].e;
        if (e.action !== "damage") continue;
        const d = parseDamage(e.raw);
        if (d && (d.target === stripAi(victim) || d.target === victim)) {
          src = d.source;
          break;
        }
      }
    }
    base.decidedBy = src ? `Commander damage from ${src}` : "Commander damage";
    return base;
  }

  // Life reached 0 (or unknown): name the source(s) of the killing swing.
  if (lethal) {
    const dom = dominantSource(lethal.p, lethal.turn, lethal.idx);
    if (dom && dom.sum * 2 >= lethal.delta) {
      base.decidedBy =
        dom.count > 1
          ? `${dom.source} ×${dom.count} (${lethal.delta} damage)`
          : `${dom.source} for ${lethal.delta}`;
      return base;
    }
    // The drop dwarfs nearby damage events (a drain / activation). Look for the
    // nearest activated or triggered source in the preceding few events.
    for (let i = lethal.idx - 1; i >= Math.max(0, lethal.idx - 10); i--) {
      const e = flat[i].e;
      if (e.action === "stack_add" && e.object) {
        base.decidedBy = `${e.object} for ${lethal.delta}`;
        return base;
      }
    }
    if (dom) {
      base.decidedBy = `${dom.source} and more (${lethal.delta} life)`;
      return base;
    }
    base.decidedBy = `${lethal.delta} life in one swing`;
    return base;
  }
  base.decidedBy = "Last opponent eliminated";
  return base;
}

/* ── commander guess ───────────────────────────────────────────────────── */

/** Best-effort commander name for a deck: the first cast card whose first word
 *  matches the deck name's first word ("Kilo Helm Final" → "Kilo, Apogee Mind").
 *  Falls back to the deck name minus trailing version noise (Alpha/Omega/B3/v2). */
export function commanderGuess(deckName: string, games?: SimGame[]): string {
  const clean = stripAi(deckName);
  const token = (clean.split(/\s+/)[0] || "").toLowerCase().replace(/[^a-z0-9'-]/g, "");
  if (token && games) {
    for (const g of games) {
      for (const t of g.turns) {
        for (const e of t.events) {
          if (e.action !== "stack_add" || !e.object || !e.raw.includes(" cast ")) continue;
          const first = e.object.split(/\s+/)[0].replace(/,$/, "").toLowerCase();
          if (first === token) return e.object;
        }
      }
    }
  }
  return clean.replace(/(\s+(alpha|omega|beta|b\d+|v\d+))+$/i, "");
}
