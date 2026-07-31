/** IP-safe mana pips (DESIGN_SYSTEM.md §4, spec §5.1). Each pip is a ringed
 *  disc with a DISTINCT inset silhouette so identity survives greyscale and
 *  colourblindness — never a WotC mana circle, never emoji, never recoloured
 *  by CSS. Pips are data: they sit beside deck names and in seat strips, and
 *  must never be placed inside a button. Always WUBRG order.
 */

const WUBRG = ["W", "U", "B", "R", "G"] as const;
type Mana = (typeof WUBRG)[number];

const NAMES: Record<Mana, string> = {
  W: "white", U: "blue", B: "black", R: "red", G: "green",
};

/* Spec markup, verbatim: disc (dark fill, coloured 1.5px ring) + silhouette. */
const PIPS: Record<Mana, React.ReactNode> = {
  W: (
    <>
      <circle cx="12" cy="12" r="11" fill="#292010" stroke="#F59E0B" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="4" fill="#FDE68A" />
      <path
        d="M12 3v3 M12 18v3 M3 12h3 M18 12h3 M5.6 5.6l2.1 2.1 M16.3 16.3l2.1 2.1 M5.6 18.4l2.1-2.1 M16.3 7.7l2.1-2.1"
        fill="none" stroke="#F59E0B" strokeWidth="1.5" strokeLinecap="round"
      />
    </>
  ),
  U: (
    <>
      <circle cx="12" cy="12" r="11" fill="#092537" stroke="#00E5FF" strokeWidth="1.5" />
      <path d="M12 4 C12 4 6 11 6 15 A6 6 0 0 0 18 15 C18 11 12 4 12 4 Z" fill="#00E5FF" />
    </>
  ),
  B: (
    <>
      <circle cx="12" cy="12" r="11" fill="#1D1526" stroke="#A855F7" strokeWidth="1.5" />
      <path d="M8 10 a4 4 0 0 1 8 0 c0 3 -1.5 4 -2 6 h-4 c-.5 -2 -2 -3 -2 -6 Z" fill="#C084FC" />
      <circle cx="10" cy="10" r="1" fill="#1D1526" />
      <circle cx="14" cy="10" r="1" fill="#1D1526" />
    </>
  ),
  R: (
    <>
      <circle cx="12" cy="12" r="11" fill="#331414" stroke="#EF4444" strokeWidth="1.5" />
      <path d="M12 4 C10 8 7 10 7 14 A5 5 0 0 0 17 14 C17 10 14 8 12 4 Z" fill="#F87171" />
      <path d="M12 9 C11 11 9.5 12 9.5 14 A2.5 2.5 0 0 0 14.5 14 C14.5 12 13 11 12 9 Z" fill="#FEF08A" />
    </>
  ),
  G: (
    <>
      <circle cx="12" cy="12" r="11" fill="#0B261A" stroke="#10B981" strokeWidth="1.5" />
      <path d="M12 4 C8 8 6 12 6 16 h12 C18 12 16 8 12 4 Z" fill="#34D399" />
      <line x1="12" y1="9" x2="12" y2="18" stroke="#0B261A" strokeWidth="1.5" />
    </>
  ),
};

export function ManaPip({ color, variant = "inline" }: { color: Mana; variant?: "inline" | "seat" }) {
  return (
    <svg
      className={`mana-badge mana-badge--${variant}`}
      viewBox="0 0 24 24"
      role="img"
      aria-label={`${NAMES[color]} mana`}
    >
      {PIPS[color]}
    </svg>
  );
}

/** A WUBRG-ordered strip of pips for a colour identity (e.g. Scryfall's
 *  color_identity array). Unknown letters are dropped; empty renders nothing. */
export function ManaPips({
  colors,
  variant = "inline",
}: {
  colors?: string[] | null;
  variant?: "inline" | "seat";
}) {
  if (!colors?.length) return null;
  const set = new Set(colors.map((c) => c.toUpperCase()));
  const ordered = WUBRG.filter((c) => set.has(c));
  if (!ordered.length) return null;
  return (
    <span className="mana-strip">
      {ordered.map((c) => (
        <ManaPip key={c} color={c} variant={variant} />
      ))}
    </span>
  );
}
