/** Display helpers shared across pages. */

/** "Ai(2)-Inspirit Omega" → "Inspirit Omega" (API_SPEC: strip prefix for display) */
export function stripAi(player: string): string {
  return player.replace(/^Ai\(\d+\)-/, "");
}

/** Seat number from a player key: "Ai(2)-X" → 2 (1-based, 0 if absent). */
export function seatOf(player: string): number {
  const m = player.match(/^Ai\((\d+)\)-/);
  return m ? Number(m[1]) : 0;
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

export function fmtDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.round(totalSeconds % 60);
  return m ? `${m} min ${s} s` : `${s} s`;
}

/** Scryfall art-crop URL for a card/commander name (hotlinked per legal posture). */
export function scryfallArt(name: string): string {
  return `https://api.scryfall.com/cards/named?exact=${encodeURIComponent(name)}&format=image&version=art_crop`;
}

/** Deck display name from a .dck filename: "kilo_helm_final.dck" → "kilo-helm-final" */
export function deckSlug(file: string): string {
  return file.replace(/\.dck$/, "").replace(/_/g, "-");
}
