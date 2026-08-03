/** Mana pips (DESIGN_SYSTEM.md §4). Ornate arcane medallions rendered from the
 *  commissioned artwork in `public/art/pips/`: a ringed frame with cardinal
 *  spikes, side sparkles and a wing flourish, each carrying a DISTINCT central
 *  silhouette (sun, droplet, skull, mountain, leaf, four-point star) so identity
 *  survives greyscale and colourblindness.
 *
 *  These ship as 96px WebP, not inline SVG. The source is painted illustration
 *  with continuous gradients and fine metalwork; vector tracing has to
 *  posterize that into flat bands, which loses the art and costs ~15x more
 *  bytes. At the 13-24px these render at, a 96px bitmap is both exact and
 *  ~7 KB. Same call the backdrop plates and the mascot make.
 *
 *  Never a WotC mana symbol, never emoji, never recoloured by CSS. Pips are
 *  data: they sit beside deck names and in seat strips, and must never be
 *  placed inside a button. Always WUBRG order.
 */

const WUBRG = ["W", "U", "B", "R", "G"] as const;
type Mana = (typeof WUBRG)[number] | "C";

const NAMES: Record<Mana, string> = {
  W: "white", U: "blue", B: "black", R: "red", G: "green", C: "colorless",
};

/** Rendered px per variant, mirroring .mana-badge--* in globals.css. */
const PX: Record<"inline" | "seat", number> = { inline: 18, seat: 20 };

const SRC: Record<Mana, string> = {
  W: "/art/pips/pip-w.webp",
  U: "/art/pips/pip-u.webp",
  B: "/art/pips/pip-b.webp",
  R: "/art/pips/pip-r.webp",
  G: "/art/pips/pip-g.webp",
  C: "/art/pips/pip-c.webp",
};

export function ManaPip({ color, variant = "inline" }: { color: Mana; variant?: "inline" | "seat" }) {
  const px = PX[variant];
  return (
    <img
      className={`mana-badge mana-badge--${variant}`}
      src={SRC[color]}
      width={px}
      height={px}
      alt={`${NAMES[color]} mana`}
      draggable={false}
    />
  );
}

/** A WUBRG-ordered strip of pips for a colour identity (e.g. Scryfall's
 *  color_identity array). Unknown letters are dropped; empty renders nothing.
 *  Colourless has no color_identity letter, so this never emits it. */
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
