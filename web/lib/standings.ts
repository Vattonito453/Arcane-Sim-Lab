/** The published win rates, read and worded (engine/standings.py).
 *
 *  Repair plan WS11 task 9, UX review problem 10: Kess read "50%" in the lede,
 *  "4 of 7, 57%" on its scorecard and "Simulated 50.0%" in the prediction
 *  table, and the results index crowned "Winner" a deck at exactly an even
 *  share. The engine now publishes one set of rates over decided games, with
 *  the digits to show and the leader, and every surface reads it through here.
 *  Nothing in this file divides wins by anything. */

import type { SimSummary, Standings, StandingsDeck } from "@/lib/types";
import { fmtRate, stripAi } from "@/lib/format";

/** The standings a payload carries. An engine older than this sends none;
 *  then they are rebuilt from the run summary the way the engine's own
 *  standings.from_summary does (every decided game has exactly one winner,
 *  and the summarizers credit a win only for such a game), so an older
 *  engine still shows the decided-game denominator, never wins over games. */
export function standingsOf(
  payload: { standings?: Standings; summary?: SimSummary | null } | null | undefined,
  roster: string[] = [],
): Standings | null {
  if (payload?.standings) return payload.standings;
  const s = payload?.summary;
  if (!s) return null;
  const wins = new Map<string, number>();
  for (const p of roster) wins.set(stripAi(p), 0);
  for (const [k, w] of Object.entries(s.wins ?? {})) {
    const name = stripAi(k);
    wins.set(name, (wins.get(name) ?? 0) + (Number(w) || 0));
  }
  const decided = [...wins.values()].reduce((a, b) => a + b, 0);
  const pod = wins.size;
  const average = pod ? 1 / pod : null;
  const decks: StandingsDeck[] = [...wins.entries()]
    .map(([deck, w]) => ({ deck, wins: w, decided, games: s.games, rate: decided ? w / decided : null }))
    .sort((a, b) => (b.rate ?? -1) - (a.rate ?? -1) || b.wins - a.wins || a.deck.localeCompare(b.deck));
  const top = decks[0];
  let leader: Standings["leader"] = { kind: "none", decks: [], rate: null };
  if (top && top.rate !== null && top.wins > 0 && (average === null || top.rate > average + 1e-9)) {
    const tops = decks.filter((d) => d.wins === top.wins && d.rate === top.rate).map((d) => d.deck);
    leader = { kind: tops.length > 1 ? "tie" : "leader", decks: tops, rate: top.rate };
  }
  const timeouts = s.timeouts ?? 0;
  return {
    version: 0,
    games: s.games,
    decided,
    undecided: {
      clock: timeouts,
      turn_cap: 0,
      draw: Math.max(0, s.games - decided - timeouts),
      no_result: 0,
    },
    pod,
    average,
    digits: decided < 30 ? 0 : 1,
    decks,
    leader,
  };
}

/** The gap between games played and games decided, said once, inline (UX
 *  review 5.2 item 1): "1 game hit the per-game clock and isn't counted."
 *  Empty when every game was decided. */
export function exclusionText(st: Standings, clockWords = "the per-game clock"): string {
  const u = st.undecided;
  const parts: [number, string, string][] = [
    [u.clock, `hit ${clockWords}`, `hit ${clockWords}`],
    [u.turn_cap, "reached the turn limit", "reached the turn limit"],
    [u.draw, "ended in a draw", "ended in a draw"],
    [u.no_result, "recorded no result", "recorded no result"],
  ];
  const live = parts.filter(([n]) => n > 0);
  const total = live.reduce((a, [n]) => a + n, 0);
  if (!total) return "";
  if (live.length === 1) {
    const [n, one, many] = live[0];
    return n === 1 ? `1 game ${one} and isn't counted.` : `${n} games ${many} and aren't counted.`;
  }
  const list = live.map(([n, one]) => `${n} ${one}`).join(", ");
  return `${total} games aren't counted: ${list}.`;
}

/** "Kess", "Kess and Stella Lee", "Kess, Stella Lee and Krenko Goblins": the
 *  one way every surface lists tied decks. */
export function andList(names: string[]): string {
  return names.length > 2
    ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`
    : names.join(" and ");
}

/** The run's leader for a list row, under the one name the title uses:
 *  "Kess", "Kess and Stella Lee (tied)", or "No clear leader". The rate is
 *  separate so a row can set it in mono. */
export function leaderOf(
  st: Standings,
  short: (deck: string) => string,
): { text: string; rate: string | null } {
  const { kind, decks, rate } = st.leader;
  if (kind === "leader" && decks.length) return { text: short(decks[0]), rate: fmtRate(rate, st.digits) };
  if (kind === "tie" && decks.length) {
    return { text: `${andList(decks.map(short))} (tied)`, rate: fmtRate(rate, st.digits) };
  }
  return { text: st.decided ? "No clear leader" : "Nothing decided", rate: null };
}

/** The true median: the middle value, and halfway between the two middle
 *  values for an even count (engine/scorecard.py med). Null for no values. */
export function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}
