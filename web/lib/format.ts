/** Display helpers shared across pages. */

/** "Ai(2)-Inspirit Omega" → "Inspirit Omega" (API_SPEC: strip prefix for display) */
export function stripAi(player: string): string {
  return player.replace(/^Ai\(\d+\)-/, "");
}

/** "Wilhelt Zombies B3" → "Wilhelt" (first word), for tight UI labels.
 *  Falls back to the full name when two decks in the pod share a first word. */
export function shortName(deckName: string, all: string[] = []): string {
  const clean = stripAi(deckName);
  const first = clean.split(/\s+/)[0];
  const clash = all.filter((o) => stripAi(o).split(/\s+/)[0] === first).length > 1;
  return clash ? clean : first;
}

/** What a run is called in the interface.
 *
 *  Runs are addressed by their result filename — "sim_20260724_094940_rotated.json"
 *  — which is meaningless to anyone reading it. The matchup is the thing people
 *  actually recognise, so that is the title; the filename stays as small mono
 *  metadata for anyone who needs to find the file on disk.
 *
 *  A pair keeps full deck names; three or four would run to ~70 characters, so
 *  those collapse to first words, which stay unambiguous via shortName().
 */
export function runTitle(deckNames: string[]): string {
  const names = deckNames.map(stripAi).filter(Boolean);
  if (names.length === 0) return "Untitled run";
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} vs ${names[1]}`;
  return names.map((n) => shortName(n, names)).join(" vs ");
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

/** Seconds a run should take, from measured Forge behaviour rather than a guess.
 *
 *  Cost is dominated by pod size, not game count: median seconds per game across
 *  real runs in engine/sim_results is ~2.5 for two decks, ~11 for three and ~52
 *  for four (four-deck games ranged 25–112s, so treat that one as soft). On top
 *  of that every run pays a fixed ~7.5s for JVM start and Forge's card database.
 *
 *  The previous flat 45 s/game told you a two-deck 16-game run would take 12
 *  minutes when it takes about half a minute.
 */
const SECONDS_PER_GAME: Record<number, number> = { 2: 2.5, 3: 11, 4: 52 };
const STARTUP_SECONDS = 7.5;

export function estimateSeconds(games: number, decks: number): number {
  const per = SECONDS_PER_GAME[decks] ?? SECONDS_PER_GAME[4];
  return STARTUP_SECONDS + games * per;
}

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
