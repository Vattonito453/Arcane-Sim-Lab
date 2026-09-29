/** A game's story in one sentence, the way a player writes up pod night
 *  (tasks/26-ux-review.md problem 1, section 5.4):
 *
 *    "Skrat's Revenge, turn 10. Out: Stella Lee and Krenko Goblins (poison,
 *     turn 9), Kess (combat, turn 10). Biggest board swing: turn 8, Ezuri's
 *     Predation."
 *
 *  Pure functions over the engine's story payload (engine/game_story.py), so
 *  the results page and the replay say exactly the same thing. Every fact is
 *  the engine's: who went out and when (dated by the lethal event Forge
 *  logged), the cause (Forge's own loss line), the killer, and the turn the
 *  winner's share of creature power grew the most. Nothing here reads a log
 *  or a card. A knockout's damage card is never shown: it is a name summed
 *  over same-named tokens and not audited (qa.knockouts, "Card"); only an
 *  alternate win's spell is, which Forge's loss line quotes.
 *
 *  Turns are table turns (a player's Nth turn is turn N), never Forge's
 *  per-player counter. Names follow shortName(), one name per deck
 *  everywhere. The display switches are applied server-side: a null cause
 *  or killer is simply left out, and a missing turning point has no clause. */

import type { GameStory, Knockout, StoryMeta, TurningPoint } from "./types";
import { seatOf, shortName, type CommanderMap } from "./format";

export interface Seg {
  text: string;
  strong?: boolean;
}

/** How a knockout is said at the table. */
const CAUSE_WORDS: Record<string, string> = {
  combat_damage: "combat",
  noncombat_damage: "non-combat damage",
  life_loss: "life loss",
  // Forge logged no life change that tells combat from life loss.
  life_total: "life reached 0",
  poison: "poison",
  commander_damage: "commander damage",
  alt_win: "alternate win",
  lose_effect: "a lose-the-game effect",
  deckout: "drew from an empty library",
  concession: "conceded",
};

export function causeWords(k: Pick<Knockout, "cause" | "card">): string | null {
  if (!k.cause || k.cause === "unknown") return null;
  // "won by spell 'Thassa's Oracle'": the card is the story.
  if (k.cause === "alt_win" && k.card) return k.card;
  return CAUSE_WORDS[k.cause] ?? null;
}

/** "A", "A and B", "A, B and C". */
function listWords(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export interface StoryInput {
  /** The game's player keys, "Ai(n)-Deck". */
  players: string[];
  /** Raw winner key, or null for a draw or a game with no result. */
  winner: string | null;
  /** The table turn the game ended on. */
  endedRound: number | null;
  /** Opening clause for a game nobody won ("Draw: hit the 15-minute clock
   *  on turn 10"), from the caller, which knows the clock. */
  noWinnerText?: string;
  story: GameStory;
}

/** The parenthetical for one knockout: cause, killer when it was not the
 *  winner, and the turn. */
function paren(k: Knockout, winner: string | null, name: (key: string) => string): string {
  const cause = causeWords(k);
  let killer: string | null = null;
  // "from its own card" (an unpaid Pact, life paid to its own spell): bare
  // "own card" after the cause read "a lose-the-game effect own card".
  if (k.by && k.by !== winner) killer = k.by === k.player ? "from its own card" : `by ${name(k.by)}`;
  const how = [cause, killer].filter(Boolean).join(" ");
  return [how, `turn ${k.round}`].filter(Boolean).join(", ");
}

function outClause(kos: Knockout[], winner: string | null, name: (key: string) => string): string {
  // Consecutive knockouts that read the same ("poison, turn 9") share one
  // parenthetical; within a group, seats in table order.
  const groups: { paren: string; members: Knockout[] }[] = [];
  for (const k of kos) {
    const p = paren(k, winner, name);
    const last = groups[groups.length - 1];
    if (last && last.paren === p) last.members.push(k);
    else groups.push({ paren: p, members: [k] });
  }
  return groups
    .map((g) => {
      const names = [...g.members]
        .sort((a, b) => seatOf(a.player) - seatOf(b.player))
        .map((k) => name(k.player));
      return `${listWords(names)} (${g.paren})`;
    })
    .join(", ");
}

export function turningPointClause(tp: TurningPoint): string {
  const what = tp.card ? `, ${tp.card}` : tp.combat ? ", in combat" : "";
  // The engine holds every inferred one since the week-3 audit fixes; the
  // mark stays for an older engine that still sends them.
  return `${tp.label}${tp.basis === "inferred" ? " (inferred)" : ""}: turn ${tp.round}${what}.`;
}

/** The label the server sends only once the turning point has passed a
 *  re-audit (MTG_TURNING_POINT=audited; engine/game_story.py LABELS). Any
 *  other label is the unaudited "Biggest board swing", which carries the
 *  audit's figure in the note below. */
const AUDITED_LABEL = "Turning point";

/** The sentence as segments (the winner strong), for rendering. */
export function storySegments(input: StoryInput, commanders?: CommanderMap): Seg[] {
  const name = (key: string) => shortName(key, input.players, commanders);
  const segs: Seg[] = [];
  if (input.winner) {
    segs.push({ text: name(input.winner), strong: true });
    segs.push({ text: input.endedRound ? `, turn ${input.endedRound}.` : " won." });
  } else {
    segs.push({ text: `${input.noWinnerText ?? "No winner"}.` });
  }
  const kos = input.story.knockouts ?? [];
  if (kos.length) segs.push({ text: ` Out: ${outClause(kos, input.winner, name)}.` });
  const tp = input.story.turning_point;
  if (input.winner && tp) segs.push({ text: ` ${turningPointClause(tp)}` });
  return segs;
}

export function storyText(input: StoryInput, commanders?: CommanderMap): string {
  return storySegments(input, commanders).map((s) => s.text).join("");
}

/** The honesty note under a list of game stories, worded for the path the
 *  stories were read on (CLAUDE.md: the shim path is a read, the stdout path
 *  is inferred, and the note must say which). */
export function storyNote(meta: StoryMeta | undefined): string {
  if (!meta) return "";
  const label = meta.turning_point_label;
  const parts: string[] = [];
  // The audit figures are studies/knockout_audit/RESULTS.md (week 3). Its
  // readers were independent model readers of the game logs, not people, so
  // the copy says "independent readings", never "a human reading".
  parts.push(
    meta.knockout_detail
      ? "Who went out, how and when comes from Forge's own loss lines, each dated by the lethal event in its log. An audit found these matched independent readings of the logs in 39 of 40 knockouts."
      : "Who went out and when comes from Forge's own log, each dated by the lethal event. How each seat went out is not shown.",
  );
  if (label) {
    const lower = label.toLowerCase();
    const audit = meta.knockout_detail ? "the same audit" : "an audit";
    // The engine shows it only where the shim's zone stream recorded the
    // board (engine/game_story.py): a stdout run's board is inferred, and its
    // swing matched the audit's readers in 1 of 8 games.
    if (meta.basis === "inferred") {
      parts.push(
        `No ${lower} is shown for this run: Forge's log records creatures leaving the battlefield but never entering, so its board is only inferred, and ${audit} found an inferred swing matched the turning point independent readers named in only 1 of 8 games.`,
      );
    } else {
      parts.push(
        `The ${lower} is the turn the winner's share of the table's creature power grew the most, read from the zone stream. It counts creatures only, at the power they entered with, so burn, auras, equipment and counters added later never move it, and a game where no turn raised that share has none.${meta.basis === "mixed" ? " Games without a zone stream show none, since their board is only inferred." : ""}`,
      );
      if (label !== AUDITED_LABEL) {
        const Audit = audit.charAt(0).toUpperCase() + audit.slice(1);
        parts.push(
          `${Audit} found it matched the turning point independent readers named in 7 of 12 such games, so read it as the biggest shift in creature power, not as the moment the game was decided.`,
        );
      }
    }
  }
  return parts.join(" ");
}
