"use client";

/** Top-down table shared by the replay theater and the live run view.
 *
 *  Renders a BoardState from lib/replay.ts — seats around a centre line with each
 *  seat's creatures pinned to the middle edge, so armies face each other the way
 *  they do on a real table. Card faces are hotlinked from Scryfall, never
 *  rehosted (frontend_architecture.md §5).
 *
 *  Two board paths. On a shim run the battlefield is READ from the zone stream
 *  (foldTo with zones); on a stock run it is INFERRED, because Forge logs cards
 *  leaving the battlefield but never entering. Callers must keep the event feed
 *  visible alongside this and keep the note under it — see <TabletopNote/>. */

import { stripAi } from "@/lib/format";
import type { BoardFxView, BoardState, Card, HandCard } from "@/lib/replay";
import { cardFace, kindFromTypes, kindOf, ptOf, type CardFacts, type Kind } from "@/lib/cards";
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
  name, n, facts, kind, attacking, blocking, tappedN, counters, attachedTo, pt,
}: {
  name: string;
  n: number;
  facts?: CardFacts;
  kind: Kind;
  /** Live P/T from the zone stream (a 5/5 token copy), else Scryfall's. */
  pt?: string;
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
    (pt ?? ptOf(facts)) ? `P/T ${pt ?? ptOf(facts)}` : null,
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

interface TileGroup { name: string; n: number; kind: Kind; pt?: string; }

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
  return (
    <div className={`tbl p${board.seats.length}`}>
      {board.seats.map((s, i) => {
        const meta = seats[i];
        const active = !!activePlayer && s.player === activePlayer;
        const cards = board.battlefield.get(s.player) ?? [];
        // This seat's declared attacks, one lane per defender, and the blocks
        // THIS seat declared. Blocks belong to the player who made them, which
        // the combat line names; they are never inferred from who was attacked.
        const lanes = board.attacks.filter((l) => l.from === s.player);
        const myBlocks = board.blocks.filter((b) => b.by === s.player);
        const attackers = lanes.flatMap((l) => l.cards);
        const blockers = myBlocks.flatMap((b) => b.blockers);
        const attackingNames = new Set(attackers);
        const blockingNames = new Set(blockers);

        // Attackers and blockers the combat lines prove are on the battlefield
        // but that Forge never logged entering — nearly always tokens. Shown,
        // because dropping them would hide real creatures. (A declared block
        // is proof of presence exactly the way a declared attack is; without
        // this, a blocking creature could carry the banner while its tile was
        // missing from the table.)
        const ghosts: string[] = [];
        {
          const proved = [...attackers, ...blockers];
          const have = new Map<string, number>();
          for (const c of cards) have.set(c.name, (have.get(c.name) ?? 0) + 1);
          for (const name of proved) {
            const k = have.get(name) ?? 0;
            if (k > 0) have.set(name, k - 1);
            else ghosts.push(name);
          }
        }
        // A lane's defender is a seat, or a planeswalker / battle by name.
        const laneLabel = (to: string) => seats.find((x) => x.player === to)?.label ?? stripAi(to);

        // Collapse duplicates, then split into the three table bands. A token
        // copy of a real card (zone stream: token=true) keeps its own tile, so
        // Saheeli's 5/5 Lightning Runner does not merge into the 2/2 original.
        const bands: TileGroup[][] = [[], [], []];
        const seen = new Map<string, TileGroup>();
        const all: Card[] = [...cards, ...ghosts.map((name) => ({ name }))];
        for (const c of all) {
          // Forge's own types when the zone stream carries them; Scryfall
          // typing otherwise (stock runs, ghosts).
          const zk = c.types ? kindFromTypes(c.types) : "unknown";
          const kind: Kind = c.token ? "token" : zk !== "unknown" ? zk : kindOf(c.name, facts(c.name));
          const key = `${kind}:${c.name}`;
          const at = seen.get(key);
          if (at) {
            at.n += 1;
            continue;
          }
          const g: TileGroup = { name: c.name, n: 1, kind, pt: c.pt };
          seen.set(key, g);
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
              {lanes.map((l) => (
                <span key={l.to} className="atkbanner">
                  {/* A split attack names who went where; a single lane reads
                      as before, the red tile borders already say who. */}
                  {lanes.length > 1
                    ? `${l.cards.join(" + ")} attacking ${laneLabel(l.to)} →`
                    : `attacking ${laneLabel(l.to)} →`}
                </span>
              ))}
              {myBlocks.length > 0 && (
                <span className="blkbanner">
                  {myBlocks.map((b, k) => (
                    <span key={`${b.attacker}-${k}`}>
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
                        key={`${g.kind}:${g.name}`}
                        name={g.name}
                        n={g.n}
                        kind={g.kind}
                        pt={g.pt}
                        facts={facts(g.name)}
                        attacking={attackingNames.has(g.name)}
                        blocking={blockingNames.has(g.name)}
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
        it reflects the board exactly at phase granularity: within the current phase a
        permanent can appear a few events before the line that created it. The event
        log remains the record of what happened.
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
