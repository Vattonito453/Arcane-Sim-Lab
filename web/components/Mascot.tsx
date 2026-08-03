/** Brand mascot (DESIGN_SYSTEM.md §6 / spec §2.2): the brass archivist, a gold
 *  artifact robot seated on a card stack holding a fan of glowing cards.
 *
 *  This is painted artwork, so it ships as a bitmap rather than inline SVG: it
 *  is one decorative illustration at a known size, the same call the backdrop
 *  plates in `public/art/` already make. Mana pips are the opposite case and
 *  stay vector (see ManaPips.tsx).
 *
 *  Below ~48px the seated figure turns to mush, so small renders swap to a
 *  head-only crop that still reads at nav size.
 */
const FULL = "/art/mascot-brass-archivist.webp";
const HEAD = "/art/mascot-brass-archivist-head.webp";

/** Natural aspect of the full artwork (556x640), so the box never distorts it. */
const FULL_ASPECT = 556 / 640;

export function Mascot({ size = 200 }: { size?: number }) {
  const head = size < 48;
  return (
    <img
      className="masthead-robot-mascot"
      src={head ? HEAD : FULL}
      alt=""
      aria-hidden="true"
      width={head ? size : Math.round(size * FULL_ASPECT)}
      height={size}
      draggable={false}
    />
  );
}
