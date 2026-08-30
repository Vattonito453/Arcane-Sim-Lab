"use client";

/** Top-down table shared by the replay theater and the live run view.
 *
 *  Renders a BoardState from lib/replay.ts — seats around a centre line with each
 *  seat's creatures pinned to the middle edge, so armies face each other the way
 *  they do on a real table. Card faces are hotlinked from Scryfall, never
 *  rehosted (frontend_architecture.md §5).
 *
 *  Board membership is INFERRED: Forge logs cards leaving the battlefield but
 *  never entering. Callers must keep the event feed visible alongside this and
 *  keep the note under it — see <TabletopNote/>. */

import { stripAi } from "@/lib/format";
import type { BoardFxView, BoardState, HandCard } from "@/lib/replay";
import { cardFace, kindOf, ptOf, type CardFacts, type Kind } from "@/lib/cards";
import { ManaPips } from "@/components/ManaPips";

export interface SeatMeta {
  player: string;
  label: string;
  art: string;
  /** Best-effort commander name — drives the seat's colour-identity pips. */
  commander?: string;
}

/** One permanent on the table. Identical copies collapse into a single tile with
 *  a count, which is what makes a 43-token board readable. */
/** Counter chip text: +1/+1 counters read as a stat delta, anything else as
 *  "n Name". Counter type names come from Forge verbatim. */
function counterChip(type: string, n: number): string {
  // Forge names the types "+1/+1" and "-1/-1" verbatim (measured; the old
  // "P1P1" guess matched nothing). Vincent: "+10/+10", not "10 +1/+1".
  if (type === "+1/+1") return `+${n}/+${n}`;
  if (type === "-1/-1") return `-${n}/-${n}`;
  return `${n} ${type.toLowerCase()}`;
}

function Tile({
  name, n, facts, kind, attacking, blocking, tappedN, counters, attachedTo,
}: {
  name: string;
  n: number;
  facts?: CardFacts;
  kind: Kind;
  attacking: boolean;
  blocking: boolean;
  tappedN: number;
  counters?: Map<string, number>;
  attachedTo?: string;
}) {
  const face = cardFace(facts);
  const allTapped = n > 0 && tappedN >= n;
  const tip = [
    name,
    facts?.type_line,
    facts?.mana_cost,
    ptOf(facts) ? `P/T ${ptOf(facts)}` : null,
    tappedN > 0 ? (allTapped ? "tapped" : `${tappedN} of ${n} tapped`) : null,
    counters && counters.size
      ? Array.from(counters, ([t, c]) => counterChip(t, c)).join(", ")
      : null,
    attachedTo ? `attached to ${attachedTo}` : null,
    blocking ? "blocking" : null,
    facts?.oracle_text,
    kind === "unknown" ? "Type unknown: no card data for this name" : null,
  ]
    .filter(Boolean)
    .join("\n");
  const cls = `tc${kind === "token" ? " tok" : ""}${kind === "unknown" ? " unk" : ""}${
    attacking ? " atk" : ""
  }${blocking ? " blk" : ""}${allTapped ? " tapd" : ""}`;
  const chips: string[] = [];
  if (counters) for (const [t, c] of counters) chips.push(counterChip(t, c));
  return (
    <span className={cls} title={tip}>
      {face ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={face} alt={name} loading="lazy" onError={(e) => e.currentTarget.remove()} />
      ) : (
        // Tokens and unidentified names have no Scryfall face to hotlink.
        <span className="nm">{name}</span>
      )}
      {n > 1 && <span className="xn">{n}</span>}
      {!allTapped && tappedN > 0 && <span className="tpn">{tappedN}T</span>}
      {chips.length > 0 && <span className="cnt">{chips.join(" ")}</span>}
      {attachedTo && <span className="att">on {attachedTo}</span>}
    </span>
  );
}

/** Battlefield split into the three bands a physical table has: the things that
 *  fight (nearest the centre), the static permanents, and the mana base. */
const BAND: Record<Kind, 0 | 1 | 2> = {
  creature: 0, token: 0, planeswalker: 0, battle: 0,
  artifact: 1, spell: 1, unknown: 1,
  land: 2,
};
const BAND_LABEL = ["", "Artifacts, enchantments and unidentified", "Lands"];
const BAND_CAP = [18, 14, 24];

interface TileGroup { name: string; n: number; kind: Kind; }

export function Tabletop({
  board, seats, activePlayer, facts, fx, hands,
}: {
  board: BoardState;
  seats: SeatMeta[];
  activePlayer: string;
  facts: (name: string) => CardFacts | undefined;
  /** Board-state stream view (taps, counters, attachments) at the playhead.
   *  Absent for results older than shim 0.12.0; every marker degrades to
   *  the previous everything-looks-untapped rendering. */
  fx?: BoardFxView;
  /** Every seat's hand at the playhead (exact, from the shim zone stream).
   *  Undefined on results without a zone stream: the band does not render. */
  hands?: Map<string, HandCard[]>;
}) {
  const blockersInPlay = new Set<string>();
  for (const b of board.blocks) for (const nm of b.blockers) blockersInPlay.add(nm);
  return (
    <div className={`tbl p${board.seats.length}`}>
      {board.seats.map((s, i) => {
        const meta = seats[i];
        const active = !!activePlayer && s.player === activePlayer;
        const cards = board.battlefield.get(s.player) ?? [];
        const atkRow = board.attacks?.from === s.player ? board.attacks : null;

        // Attackers and blockers the combat lines prove are on the battlefield
        // but that Forge never logged entering — nearly always tokens. Shown,
        // because dropping them would hide real creatures. (A declared block
        // is proof of presence exactly the way a declared attack is; without
        // this, a blocking creature could carry the banner while its tile was
        // missing from the table.)
        const ghosts: string[] = [];
        {
          const proved: string[] = [];
          if (atkRow) proved.push(...atkRow.cards);
          if (board.attacks && board.attacks.to === s.player) {
            for (const b of board.blocks) proved.push(...b.blockers);
          }
          const have = new Map<string, number>();
          for (const c of cards) have.set(c.name, (have.get(c.name) ?? 0) + 1);
          for (const name of proved) {
            const k = have.get(name) ?? 0;
            if (k > 0) have.set(name, k - 1);
            else ghosts.push(name);
          }
        }
        const defender = atkRow
          ? (seats.find((x) => x.player === atkRow.to)?.label ?? stripAi(atkRow.to))
          : null;
        // Blocks render on the DEFENDING seat: these are its creatures
        // stepping in front of the incoming attack.
        const isDefender = !!board.attacks && board.attacks.to === s.player;

        // Collapse duplicates, then split into the three table bands.
        const bands: TileGroup[][] = [[], [], []];
        const seen = new Map<string, TileGroup>();
        for (const c of [...cards, ...ghosts.map((name) => ({ name }))]) {
          const kind = kindOf(c.name, facts(c.name));
          const at = seen.get(c.name);
          if (at) {
            at.n += 1;
            continue;
          }
          const g: TileGroup = { name: c.name, n: 1, kind };
          seen.set(c.name, g);
          bands[BAND[kind]].push(g);
        }

        // Top-row seats face down the page; bottom-row seats face up.
        const far = board.seats.length <= 2 ? i === 0 : i < 2;
        const hand = hands?.get(s.player);
        const handN = hand ? hand.reduce((a, h) => a + h.n, 0) : 0;

        return (
          <div
            key={s.player}
            className={`parea${far ? " far" : ""}${s.eliminated ? " gone" : ""}${
              active ? " act" : ""
            }`}
          >
            <div className="plate">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={meta?.art} alt="" onError={(e) => e.currentTarget.remove()} />
              <span className="pn">{meta?.label ?? stripAi(s.player)}</span>
              {/* Identity is data (pips beside the name), never a control. */}
              {meta?.commander && (
                <ManaPips colors={facts(meta.commander)?.color_identity} variant="seat" />
              )}
              {active && <em>· active</em>}
              {s.eliminated ? (
                <span className="pnums">
                  <span className="st out">
                    <i />
                    Out round {s.eliminated.round}
                  </span>
                </span>
              ) : (
                <span className="pnums">
                  <b>{s.life}</b> life · {cards.length} on board
                  {(s.poison ?? 0) > 0 && <> · {s.poison} poison</>}
                </span>
              )}
            </div>

            {hand && (
              <div className="zone hand">
                <span className="zlab">Hand ({handN})</span>
                {hand.map((h) => (
                  <Tile
                    key={h.name}
                    name={h.name}
                    n={h.n}
                    kind={kindOf(h.name, facts(h.name))}
                    facts={facts(h.name)}
                    attacking={false}
                    blocking={false}
                    tappedN={0}
                  />
                ))}
              </div>
            )}
            <div className="zones">
              {/* First child, so the reverse that `far` applies puts it on the
                  centre edge for both rows of seats. */}
              {atkRow && <span className="atkbanner">attacking {defender} →</span>}
              {isDefender && board.blocks.length > 0 && (
                <span className="blkbanner">
                  {board.blocks.map((b) => (
                    <span key={b.attacker}>
                      {b.blockers.join(" + ")} {b.blockers.length === 1 ? "blocks" : "block"} {b.attacker}
                    </span>
                  ))}
                </span>
              )}
              {bands.map((band, b) => {
                if (!band.length) return null;
                const shown = band.slice(0, BAND_CAP[b]);
                const extra = band.length - shown.length;
                return (
                  <div key={b} className={`zone${b === 2 ? " lands" : ""}`}>
                    {BAND_LABEL[b] && <span className="zlab">{BAND_LABEL[b]}</span>}
                    {shown.map((g) => (
                      <Tile
                        key={g.name}
                        name={g.name}
                        n={g.n}
                        kind={g.kind}
                        facts={facts(g.name)}
                        attacking={!!atkRow && atkRow.cards.includes(g.name)}
                        blocking={isDefender && blockersInPlay.has(g.name)}
                        tappedN={Math.min(g.n, fx?.tappedByName.get(g.name) ?? 0)}
                        counters={fx?.countersByName.get(g.name)}
                        attachedTo={fx?.attachTo.get(g.name)}
                      />
                    ))}
                    {extra > 0 && <span className="zmore">+{extra}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** The honesty note that must accompany the table wherever it is shown.
 *
 *  There are two board paths and they do not deserve the same sentence. On a
 *  shim run the zone stream records every permanent entering AND leaving play,
 *  so the table is a read (measured: exit_match_rate 1.0, assumed_share 0.0).
 *  On a stock Forge run only exits are logged and the table is inferred at
 *  about 86% exit match. Showing the inference disclaimer on a shim run is not
 *  safely conservative: it tells the user the data is worse than it is, which
 *  is the same class of error as overclaiming. Pass read only when the game
 *  actually carries a zone stream. */
export function TabletopNote({ read = false }: { read?: boolean }) {
  if (read) {
    return (
      <p className="tblnote">
        Card faces come from Scryfall. This table is read from the zone stream the
        simulator emits, which records every permanent entering and leaving play, so
        it reflects the board exactly. The event log remains the record of what
        happened.
      </p>
    );
  }
  return (
    <p className="tblnote">
      Card faces come from Scryfall. Which permanents are on the table is
      reconstructed from the event log rather than read from it. Forge logs cards leaving
      the battlefield but not entering, so treat the table as an aid and the event
      log as the record.
    </p>
  );
}
