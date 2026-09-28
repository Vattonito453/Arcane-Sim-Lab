/** Display helpers shared across pages. */

/** "Ai(2)-Inspirit Omega" → "Inspirit Omega" (API_SPEC: strip prefix for display) */
export function stripAi(player: string): string {
  return player.replace(/^Ai\(\d+\)-/, "");
}

/** {deck name: [commanders]}, as the engine reads them from each deck's own
 *  [Commander] section (engine/commanders.py). */
export type CommanderMap = Record<string, string[]>;

/** The part of a deck name before its first comma, when that part IS the
 *  commander's name: the commander's full name, the part of it before its
 *  own comma, or its leading words ("Kess" for Kess, Dissident Mage;
 *  "Stella Lee" for Stella Lee, Wild Card; "Edgar" for Edgar Markov). */
function commanderHead(deck: string, commanders: string[] | undefined): string | null {
  const at = deck.indexOf(",");
  if (at <= 0 || !commanders?.length) return null;
  const head = deck.slice(0, at).trim();
  if (!head) return null;
  const hit = commanders.some((c) => {
    const name = c.trim();
    return name === head || name.split(",")[0].trim() === head || name.startsWith(`${head} `);
  });
  return hit ? head : null;
}

/** A deck's one name, used everywhere it appears (tasks/26-ux-review.md,
 *  problem 5): the deck's own name, as on Moxfield and Archidekt. When the
 *  part before a comma is the commander's name, what follows the comma drops:
 *  "Kess, Reanimator" (Kess, Dissident Mage) is "Kess", "Stella Lee, Wild
 *  Card" is "Stella Lee"; "Skrat's Revenge" and "Krenko Goblins" stay as
 *  they are.
 *
 *  The old rule kept the first whitespace token, comma included, which put
 *  "Kess, vs Stella vs Skrat's vs Krenko" in the report's h1 and "Kess," on a
 *  seat plate. Commanders come from the engine, never from a guess, so
 *  without them (an older engine, a deck file that is gone) the full name
 *  stands. Two decks whose short names collide both keep their full names. */
export function shortName(deckName: string, all: string[] = [], commanders?: CommanderMap): string {
  const clean = stripAi(deckName);
  const short = (n: string) => commanderHead(n, commanders?.[n]) ?? n;
  const mine = short(clean);
  if (mine === clean) return clean;
  const others = Array.from(new Set(all.map(stripAi))).filter((o) => o !== clean);
  return others.some((o) => short(o) === mine) ? clean : mine;
}

/** What a run is called in the interface.
 *
 *  Runs are addressed by their result filename — "sim_20260724_094940_rotated.json"
 *  — which is meaningless to anyone reading it. The matchup is the thing people
 *  actually recognise, so that is the title; the filename stays as small mono
 *  metadata for anyone who needs to find the file on disk.
 *
 *  One name per deck, the same one every other surface uses (shortName):
 *  "Kess vs Skrat's Revenge vs Stella Lee vs Krenko Goblins".
 */
export function runTitle(deckNames: string[], commanders?: CommanderMap): string {
  const names = deckNames.map(stripAi).filter(Boolean);
  if (names.length === 0) return "Untitled run";
  return names.map((n) => shortName(n, names, commanders)).join(" vs ");
}

/** Seat number from a player key: "Ai(2)-X" → 2 (1-based, 0 if absent). */
export function seatOf(player: string): number {
  const m = player.match(/^Ai\((\d+)\)-/);
  return m ? Number(m[1]) : 0;
}

/** "1 game" / "2 games". Counting nouns show up all over this UI and "1 games"
 *  was reaching the screen in four places. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function timeAgo(unixSeconds: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - unixSeconds));
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.floor(h / 24);
  return `${d} d ago`;
}

export function fmtDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

/** Short calendar day: "1 Aug 2026". */
export function fmtDay(d: Date): string {
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** The run date, read out of the result filename.
 *
 *  Runs are addressed by a timestamped name — "sim_20260801_193328.json". The
 *  filename is an address and has no business being on screen, but the
 *  timestamp inside it is the one thing that distinguishes two runs of the same
 *  matchup, and the summary payload carries no date of its own. So the date is
 *  lifted out and the address stays in the details disclosure. Returns null for
 *  any filename that isn't this shape.
 */
export function runDate(file: string): Date | null {
  const m = file.match(/(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})/);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m;
  const dt = new Date(+y, +mo - 1, +d, +h, +mi, +s);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

/** "14 min", "3 min 20 s", "45 s".
 *
 *  Rounds the total BEFORE splitting. Rounding the remainder separately printed
 *  "13 min 60 s" for 839.5 s (and "60 s" for 59.7), because 59.5 rounds up to a
 *  full minute that never carried. Whole minutes drop the " 0 s" tail. */
export function fmtDuration(totalSeconds: number): string {
  const total = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (!m) return `${s} s`;
  return s ? `${m} min ${s} s` : `${m} min`;
}

/** Scryfall art-crop URL for a card/commander name (hotlinked per legal posture). */
export function scryfallArt(name: string): string {
  return `https://api.scryfall.com/cards/named?exact=${encodeURIComponent(name)}&format=image&version=art_crop`;
}

/** A typical-duration range in the words a person uses.
 *
 *  "40 to 105 minutes", or "1.5 to 4 hours" once the top end passes two hours;
 *  `short` gives "40–105 min" / "1.5–4 h" for the narrow run bar. The low end
 *  rounds down and the high end up, so the range never claims more precision
 *  than the engine's 0.6x to 1.6x spread has.
 *
 *  The numbers always come from the engine (GET /estimate, or /sim-status
 *  progress.typical_seconds). The web used to keep its own per-game table,
 *  measured on stock Forge, and quoted "about 14 min" for a 4-deck, 8-game job
 *  that took 55 min 56 s (tasks/26-ux-review.md, problem 4). Never again: there
 *  is one estimate, and it lives in engine/mtg_engine.py estimate_sim_seconds. */
export function fmtRange(lowSeconds: number, highSeconds: number, short = false): string {
  if (!Number.isFinite(lowSeconds) || !Number.isFinite(highSeconds)) return "–";
  const lowMin = Math.max(1, Math.floor(lowSeconds / 60));
  const highMin = Math.max(lowMin + 1, Math.ceil(highSeconds / 60));
  if (highMin <= 120) return short ? `${lowMin}–${highMin} min` : `${lowMin} to ${highMin} minutes`;
  // Half-hour steps: "1.5 to 4 hours" reads; "81 to 211 minutes" does not.
  const lowH = Math.max(0.5, Math.floor(lowSeconds / 1800) / 2);
  const highH = Math.max(lowH + 0.5, Math.ceil(highSeconds / 1800) / 2);
  return short ? `${lowH}–${highH} h` : `${lowH} to ${highH} hours`;
}

/** "once", "twice", "four times": how often each deck takes the first seat. */
export function timesWord(n: number): string {
  const words: Record<number, string> = {
    1: "once", 2: "twice", 3: "three times", 4: "four times", 8: "eight times",
  };
  return words[n] ?? `${n} times`;
}

/** What a player sees when the engine does not answer.
 *
 *  Operator detail (the command that starts the engine, env var names, the
 *  engine address setting) is for whoever runs the server, never for players
 *  (tasks/26-ux-review.md, problem 6). Gate it with a literal
 *  `process.env.NODE_ENV !== "production"` at the use site, not an exported
 *  flag: Next inlines NODE_ENV at build time, and only a literal comparison lets
 *  the minifier drop the operator text from the production bundle. An imported
 *  constant still rendered nothing, but shipped the strings. */
export const SERVER_DOWN =
  "Sim Lab's server isn't answering. Your decks and sims are safe. Try again in a minute.";

/** Readable deck name from whatever the job payload carries.
 *
 *  A job's `decks` are the paths /simulate was handed, and in a container those
 *  are absolute: "/data/decks/ant-man-396be140.dck". Slugging that without
 *  stripping the directory put
 *  "/data/decks/ant-man-396be140 vs /app/engine/decks/atraxa-counters" in the
 *  run page's H1 — a filesystem path as a page title, and it leaked the image
 *  layout too. Take the basename, drop the extension and the import hash
 *  suffix, then space out the separators.
 *
 *    "/data/decks/ant-man-396be140.dck" → "Ant Man"
 *    "kilo_helm_final.dck"              → "Kilo Helm Final"
 */
export function deckSlug(file: string): string {
  const base = file.split(/[\\/]/).pop() ?? file;
  return base
    .replace(/\.dck$/i, "")
    // Imported decks get an 8-hex uniqueness suffix; it is an address, not a name.
    .replace(/-[0-9a-f]{8}$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** A deck's display name from whatever meta.decks holds.
 *
 *  meta.decks carries CONTAINER paths ("/data/decks/skrat_s_revenge_239c6293.dck"),
 *  and pages were rendering them with only the extension stripped, so a deck
 *  picker read "/data/decks/skrat s revenge 239c6293". The engine now sends
 *  exact names in summary.deck_labels; this is the fallback for an older
 *  engine, and it must never show a path. */
export function deckLabel(raw: string): string {
  const base = raw.split(/[\\/]/).pop() ?? raw;
  return base
    .replace(/\.dck$/i, "")
    .replace(/_[0-9a-f]{8}$/i, "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
