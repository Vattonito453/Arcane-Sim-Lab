/** Card facts from the engine's Scryfall cache (GET /cards).
 *
 *  These are STATIC facts — type line, P/T, mana cost, oracle text, art. They are
 *  what let the board group itself into lands / creatures / artifacts and show
 *  real power/toughness; without a type line the replay can't tell a permanent
 *  from a one-shot spell. Dynamic truth (what actually happened) always comes
 *  from the event log, never from here.
 */
import { apiBase } from "./api";

export interface CardFacts {
  name: string;
  type_line: string;
  mana_cost?: string;
  cmc?: number;
  power?: string | null;
  toughness?: string | null;
  oracle_text?: string;
  colors?: string[];
  color_identity?: string[];
  art_crop?: string | null;
  normal?: string | null;
  scryfall_uri?: string;
}

export type CardMap = Record<string, CardFacts>;

/** Mirrors engine/cards.py normalize_name so client and server agree on keys. */
export function normalizeName(raw: string): string {
  let s = raw.trim();
  s = s.split(/\s+-\s+/)[0];
  s = s.replace(/\s*\(\d+\)\s*$/, "");
  s = s.replace(/\s*\([A-Z0-9]{2,6}\)\s*[\w★]*$/, "");
  return s.trim();
}

export function isToken(name: string): boolean {
  return /\bTokens?\b/i.test(normalizeName(name));
}

/** Coarse grouping used for board rows. Mirrors engine/cards.py card_kind. */
export type Kind =
  | "land" | "creature" | "artifact" | "planeswalker" | "battle"
  | "token" | "spell" | "unknown";

export function kindOf(name: string, facts?: CardFacts): Kind {
  if (isToken(name)) return "token";
  const tl = facts?.type_line ?? "";
  if (!tl) return "unknown";
  if (tl.includes("Land")) return "land";
  if (tl.includes("Creature")) return "creature";
  if (tl.includes("Planeswalker")) return "planeswalker";
  if (tl.includes("Battle")) return "battle";
  if (tl.includes("Artifact") || tl.includes("Enchantment")) return "artifact";
  if (tl.includes("Instant") || tl.includes("Sorcery")) return "spell";
  return "unknown";
}

/** Display order for grouped board rows — mirrors a physical table layout. */
export const KIND_ORDER: Kind[] = [
  "creature", "token", "planeswalker", "battle", "artifact", "unknown", "spell", "land",
];

export const KIND_LABEL: Record<Kind, string> = {
  creature: "Creatures",
  token: "Tokens",
  planeswalker: "Planeswalkers",
  battle: "Battles",
  artifact: "Artifacts and enchantments",
  land: "Lands",
  spell: "Spells",
  unknown: "Unidentified",
};

export function ptOf(facts?: CardFacts): string | null {
  if (!facts?.power && !facts?.toughness) return null;
  return `${facts.power ?? "?"}/${facts.toughness ?? "?"}`;
}

/** Card face for the tabletop, hotlinked from Scryfall (never rehosted).
 *
 *  A 4-player board can hold 60+ permanents, and `normal` is 488x680 each — far
 *  more pixels than a 54px-wide tile can use. Scryfall serves the same face at
 *  every size off one path, so swapping the size segment gets the ~9x smaller
 *  `small` render without a second field in the cache or a refetch of the
 *  thousands of cards already stored with only `normal`. Falls back to `normal`
 *  if that path shape ever changes, and to null so the tile renders name-only.
 */
export function cardFace(facts?: CardFacts): string | null {
  const normal = facts?.normal;
  if (!normal) return null;
  return normal.includes("/normal/") ? normal.replace("/normal/", "/small/") : normal;
}

/** In-session memo so scrubbing a replay never refetches the same names. */
const memo: CardMap = {};
const missing = new Set<string>();

export function known(name: string): CardFacts | undefined {
  return memo[normalizeName(name).toLowerCase()];
}

/** Fetch facts for these names, skipping tokens and anything already known. */
export async function loadCards(names: string[]): Promise<CardMap> {
  const want = Array.from(
    new Set(
      names
        .map(normalizeName)
        .filter((n) => n && !isToken(n))
        .filter((n) => !(n.toLowerCase() in memo) && !missing.has(n.toLowerCase())),
    ),
  );
  if (!want.length) return memo;

  // Chunked so the query string stays a sane length.
  for (let i = 0; i < want.length; i += 60) {
    const chunk = want.slice(i, i + 60);
    try {
      const r = await fetch(
        `${apiBase()}/cards?names=${encodeURIComponent(chunk.join("|"))}`,
        { cache: "no-store" },
      );
      if (!r.ok) break;
      const data: { cards: CardMap; missing?: string[] } = await r.json();
      for (const [k, v] of Object.entries(data.cards ?? {})) {
        memo[k.toLowerCase()] = v;
      }
      for (const m of data.missing ?? []) missing.add(m.toLowerCase());
    } catch {
      break; // engine or Scryfall unreachable — the UI degrades to names only
    }
  }
  return memo;
}
