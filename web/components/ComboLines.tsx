"use client";

/** Combo lines (from Commander Spellbook): the results-page stopgap.
 *
 *  WHY THIS CHANGED (repair plan WS11 task 2, UX review problem 2). The old
 *  table listed one row per Spellbook variant under a heading that called
 *  them the deck's way to win: 28 near-duplicate rows for one deck, engines
 *  (infinite mana, storm, ETB) badged as lines the AI could fire whenever the
 *  deck won later by any means, and a 1692px table inside a 1196px scroller
 *  at 1440. Most Spellbook lines cannot win on their own, and Forge's AI does
 *  not run combo loops, so the table can only show whether the pieces came
 *  together: chances, not results.
 *
 *  What the stopgap does, all client-side over the existing /analysis payload:
 *   - Folds variants into families: same `produces` (as a set) and sharing all
 *     but one card, joined transitively. A family that is a clean product of
 *     alternatives ("one of 2" x "one of 6") is written as slots.
 *   - Family figures count ANY variant: games any variant was together, games
 *     won after that, and the draw-odds expectation of having drawn every piece
 *     of at least one variant, computed exactly by inclusion-exclusion from the
 *     per-game cards-seen counts the engine already ships. Summing per-variant
 *     expectations would overcount; taking the largest would undercount (12
 *     Squirrel Girl variants at ~0.2 each are a family at ~1.6).
 *   - Folds families with 0 assemblies and under one expected game behind a
 *     visible "never came together" toggle.
 *   - Shows produces as chips, and Spellbook's description and prerequisites
 *     behind a labelled Details button (they used to be a hover-only title).
 *
 *  WS8/WS12 replace this with Spellbook's own families (`of`) and five bands.
 *  All styling comes from globals.css; this file adds none. */

import { Fragment, useState } from "react";
import { PageDetails } from "@/components/Chrome";
import { plural } from "@/lib/format";
import type { AnalysedCombo, AnalysisDeck, AnalysisReport } from "@/lib/types";

const SPELLBOOK = "https://commanderspellbook.com/combo/";
/** Past this many variants the general inclusion-exclusion (2^n terms) is not
 *  worth running; a clean product family is still exact at any size. */
const MAX_GENERAL_VARIANTS = 12;

/** Front face, lowercased: the form card names are compared in. */
function norm(name: string): string {
  return name.split(" // ")[0].trim().toLowerCase();
}

/** Chance that c specific singletons are all among n cards seen from an
 *  N-card library while m other specific singletons are all not. */
function pSeen(n: number, N: number, c: number, m: number): number {
  const seen = Math.min(n, N);
  if (seen < c || c + m > N) return 0;
  let p = 1;
  for (let i = 0; i < c; i++) p *= (seen - i) / (N - i);
  for (let j = 0; j < m; j++) p *= (N - seen - j) / (N - c - j);
  return Math.max(0, p);
}

function popcount(x: number): number {
  let n = 0;
  for (let v = x >>> 0; v; v &= v - 1) n++;
  return n;
}

interface Family {
  key: string;
  variants: AnalysedCombo[];
  /** The first variant's produces, in Spellbook's order. */
  produces: string[];
  /** Cards in every variant, in the first variant's order. */
  core: string[];
  /** Alternatives, when the family is a clean product of them; else null. */
  slots: string[][] | null;
  /** Cards each variant adds to the core (0 for a single line). */
  extra: number;
  gamesPlayed: number;
  /** Games in which every piece of at least one variant was together. */
  assembled: number;
  /** Of those, games the deck won. */
  won: number;
  /** Median of each assembled game's earliest assembled turn. */
  medianTurn: number | null;
  /** Games raw draw odds predicted every piece of at least one variant. */
  expected: number | null;
  /** True when `expected` is only a lower bound (largest single variant). */
  expectedFloor: boolean;
  missing: { label: string; n: number } | null;
  /** Turns one variant sat together in games the deck did not win (largest). */
  idle: number;
  spellPieces: string[];
}

/** Slots for a family whose non-core cards form a clean product: every
 *  variant takes exactly one card from each slot, and every combination is
 *  present. Cards that never appear together in a variant share a slot. */
function productSlots(variants: AnalysedCombo[], core: Set<string>, extra: number): string[][] | null {
  if (extra === 0) return [];
  const rest = variants.map((v) => v.cards.filter((c) => !core.has(c)));
  if (extra === 1) return [rest.map((r) => r[0])];
  const cardsInOrder: string[] = [];
  for (const r of rest) for (const c of r) if (!cardsInOrder.includes(c)) cardsInOrder.push(c);
  const together = new Set<string>();
  for (const r of rest) for (const a of r) for (const b of r) if (a !== b) together.add(`${a}\u0001${b}`);
  // Union cards that never co-occur.
  const parent = new Map<string, string>();
  for (const c of cardsInOrder) parent.set(c, c);
  const find = (c: string): string => {
    let x = c;
    while (parent.get(x) !== x) x = parent.get(x) as string;
    return x;
  };
  for (const a of cardsInOrder)
    for (const b of cardsInOrder)
      if (a < b && !together.has(`${a}\u0001${b}`)) parent.set(find(a), find(b));
  const groups = new Map<string, string[]>();
  for (const c of cardsInOrder) {
    const root = find(c);
    groups.set(root, [...(groups.get(root) ?? []), c]);
  }
  const slots = [...groups.values()];
  if (slots.length !== extra) return null;
  const product = slots.reduce((acc, s) => acc * s.length, 1);
  if (product !== variants.length) return null;
  for (const r of rest) {
    for (const s of slots) if (r.filter((c) => s.includes(c)).length !== 1) return null;
  }
  // Short lists first: "one of 2 + one of 6" reads better than the reverse.
  return slots.sort((a, b) => a.length - b.length);
}

/** Per-game chance that every piece of at least one variant was drawn. */
function familyGameP(
  fam: { variants: AnalysedCombo[]; core: string[]; slots: string[][] | null },
  seen: number,
  deckSize: number,
  cmdrs: Set<string>,
): number | null {
  const lib = (c: string) => !cmdrs.has(norm(c));
  if (fam.slots) {
    // P(core all drawn, and at least one card of each slot drawn), by
    // inclusion-exclusion over the slots left out. A slot holding the
    // commander is always met: the command zone makes it available.
    const c = fam.core.filter(lib).length;
    const sizes = fam.slots.filter((s) => s.every(lib)).map((s) => s.length);
    let p = 0;
    for (let mask = 0; mask < 1 << sizes.length; mask++) {
      let m = 0;
      for (let k = 0; k < sizes.length; k++) if (mask & (1 << k)) m += sizes[k];
      p += (popcount(mask) % 2 ? -1 : 1) * pSeen(seen, deckSize, c, m);
    }
    return p;
  }
  // General case: P(union of "every piece of variant v drawn").
  const n = fam.variants.length;
  if (n > MAX_GENERAL_VARIANTS) return null;
  const index = new Map<string, number>();
  const vmask = fam.variants.map((v) => {
    let mask = 0;
    for (const card of v.cards.filter(lib)) {
      if (!index.has(card)) index.set(card, index.size);
      mask |= 1 << (index.get(card) as number);
    }
    return mask >>> 0;
  });
  if (index.size > 30) return null;
  const union = new Array<number>(1 << n).fill(0);
  let p = 0;
  for (let mask = 1; mask < 1 << n; mask++) {
    const low = mask & -mask;
    union[mask] = (union[mask ^ low] | vmask[31 - Math.clz32(low)]) >>> 0;
    p += (popcount(mask) % 2 ? 1 : -1) * pSeen(seen, deckSize, popcount(union[mask]), 0);
  }
  return p;
}

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
}

function buildFamily(variants: AnalysedCombo[], deck: AnalysisDeck, cmdrs: Set<string>): Family {
  const first = variants[0];
  const coreSet = new Set(first.cards.filter((c) => variants.every((v) => v.cards.includes(c))));
  const core = first.cards.filter((c) => coreSet.has(c));
  const extra = first.cards.length - core.length;
  const slots = variants.length === 1 ? [] : productSlots(variants, coreSet, extra);

  // Figures over ANY variant, keyed by game number.
  const earliest = new Map<number, number>();
  const wonGames = new Set<number>();
  const avail = new Map<number, Map<string, boolean>>();
  for (const v of variants) {
    for (const g of v.games ?? []) {
      if (g.assembled_turn != null) {
        const prev = earliest.get(g.n);
        earliest.set(g.n, prev == null ? g.assembled_turn : Math.min(prev, g.assembled_turn));
        if (g.won) wonGames.add(g.n);
      }
      const a = avail.get(g.n) ?? new Map<string, boolean>();
      for (const [card, turn] of Object.entries(g.pieces ?? {})) a.set(card, (a.get(card) ?? false) || turn !== null);
      avail.set(g.n, a);
    }
  }

  // Which requirement held the family up most often: a core card, or a whole
  // slot of alternatives with none available.
  const reqs: { label: string; cards: string[] }[] = core.map((c) => ({ label: c, cards: [c] }));
  for (const s of slots ?? []) reqs.push({ label: `any of ${s.join(" / ")}`, cards: s });
  let missing: Family["missing"] = null;
  for (const r of reqs) {
    let n = 0;
    for (const a of avail.values()) if (!r.cards.some((c) => a.get(c))) n++;
    if (n > 0 && (!missing || n > missing.n)) missing = { label: r.label, n };
  }

  // Draw-odds expectation for the family.
  let expected: number | null = null;
  let expectedFloor = false;
  if (variants.length === 1) {
    expected = first.expected_drawn_games ?? null;
  } else {
    const deckSize = deck.deck_size ?? 99;
    let sum = 0;
    let ok = (first.games ?? []).length > 0;
    for (const g of first.games ?? []) {
      const p = g.cards_seen == null ? null : familyGameP({ variants, core, slots }, g.cards_seen, deckSize, cmdrs);
      if (p == null) {
        ok = false;
        break;
      }
      sum += p;
    }
    if (ok) {
      expected = Math.round(sum * 10) / 10;
    } else {
      const each = variants.map((v) => v.expected_drawn_games).filter((x): x is number => x != null);
      expected = each.length ? Math.max(...each) : null;
      expectedFloor = expected != null;
    }
  }

  const spellPieces: string[] = [];
  for (const v of variants) for (const c of v.nonpermanent_pieces ?? []) if (!spellPieces.includes(c)) spellPieces.push(c);

  return {
    key: first.id || first.cards.join(" + "),
    variants,
    produces: first.produces,
    core,
    slots,
    extra,
    gamesPlayed: first.games_played,
    assembled: earliest.size,
    won: wonGames.size,
    medianTurn: median([...earliest.values()]),
    expected,
    expectedFloor,
    missing,
    idle: Math.max(0, ...variants.map((v) => v.idle_online_turns ?? 0)),
    spellPieces,
  };
}

/** Variants fold together when Spellbook lists the same results for them and
 *  they share all but one card; the relation is joined transitively, so a
 *  "one of 2" x "one of 6" family lands in one row. */
function familiesOf(deck: AnalysisDeck): Family[] {
  const combos = deck.combos;
  const cmdrs = new Set((deck.commanders ?? []).map(norm));
  const producesKey = (c: AnalysedCombo) =>
    [...new Set(c.produces.map((p) => p.toLowerCase()))].sort().join("\u0001");
  const parent = combos.map((_, i) => i);
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  for (let i = 0; i < combos.length; i++) {
    for (let j = i + 1; j < combos.length; j++) {
      const a = combos[i];
      const b = combos[j];
      if (a.cards.length !== b.cards.length || a.cards.length < 2) continue;
      if (producesKey(a) !== producesKey(b)) continue;
      const shared = a.cards.filter((c) => b.cards.includes(c)).length;
      if (shared === a.cards.length - 1) parent[find(i)] = find(j);
    }
  }
  const groups = new Map<number, AnalysedCombo[]>();
  combos.forEach((c, i) => {
    const root = find(i);
    groups.set(root, [...(groups.get(root) ?? []), c]);
  });
  return [...groups.values()].map((vs) => buildFamily(vs, deck, cmdrs));
}

/** Never together, and draw odds said under one game in the whole run: a zero
 *  here is the expected outcome, not a finding, so it folds away. A lower
 *  bound under one proves nothing, so a floor never folds. */
function neverCameTogether(f: Family): boolean {
  return f.assembled === 0 && f.expected != null && !f.expectedFloor && f.expected < 1;
}

function fmtExpected(f: Family): string {
  if (f.expected == null) return "–";
  return f.expectedFloor ? `at least ${f.expected.toFixed(1)}` : `~${f.expected.toFixed(1)}`;
}

/** The line itself: its cards, Spellbook's results as chips, and the Details
 *  control. The control sits in this cell, beside what it expands, rather
 *  than in a last column: on a phone the table scrolls sideways, and a last
 *  column's button is off-screen until the reader finds the scroll. */
function LineCell({
  f,
  cmdrs,
  open,
  controls,
  onToggle,
}: {
  f: Family;
  cmdrs: Set<string>;
  open: boolean;
  controls: string;
  onToggle: () => void;
}) {
  const card = (c: string) => (
    <span className="cl-card">
      {c}
      {cmdrs.has(norm(c)) && <span className="cl-role"> (commander)</span>}
    </span>
  );
  const parts: React.ReactNode[] = f.core.map((c) => <Fragment key={`c-${c}`}>{card(c)}</Fragment>);
  if (f.slots) {
    for (const [i, s] of f.slots.entries()) {
      parts.push(
        <span key={`s-${i}`} className="cl-slot">
          <span className="combo-sep">one of </span>
          {s.map((c, k) => (
            <Fragment key={c}>
              {k > 0 && <span className="combo-sep"> / </span>}
              {card(c)}
            </Fragment>
          ))}
        </span>,
      );
    }
  } else if (f.extra > 0) {
    parts.push(
      <span key="varies" className="ctanote">
        {plural(f.extra, "more card")}, different in each variant (listed under Details)
      </span>,
    );
  }
  return (
    <>
      <div className="cl-cards">
        {parts.map((p, i) => (
          <Fragment key={i}>
            {i > 0 && <span className="combo-sep"> + </span>}
            {p}
          </Fragment>
        ))}
      </div>
      {f.produces.length > 0 && (
        <ul className="cl-chips" aria-label="Commander Spellbook lists these results">
          {f.produces.map((p) => (
            <li key={p} className="cl-chip">
              {p}
            </li>
          ))}
        </ul>
      )}
      <div className="cl-meta">
        {f.variants.length > 1 && <span>{f.variants.length} variants Commander Spellbook lists separately</span>}
        <button
          type="button"
          className="cl-toggle"
          aria-expanded={open}
          aria-controls={controls}
          onClick={onToggle}
        >
          Details
        </button>
      </div>
    </>
  );
}

function DetailCell({ f }: { f: Family }) {
  // The variant whose steps are shown: one that came together, else the first.
  const rep = f.variants.find((v) => v.assembled_games > 0) ?? f.variants[0];
  const many = f.variants.length > 1;
  return (
    <div className="cl-detail-body cl-sticky">
      {many && (
        <div className="cl-dblock">
          <div className="cl-dh">The {f.variants.length} variants</div>
          <ul className="cl-variants">
            {f.variants.map((v) => (
              <li key={v.id}>
                {v.cards.join(" + ")}
                <span className="cl-vstat">
                  assembled {v.assembled_games} of {v.games_played}
                  {v.expected_drawn_games != null && <>, ~{v.expected_drawn_games} from draws</>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="cl-dblock">
        <div className="cl-dh">
          How it works, from Commander Spellbook{many ? ` (shown for ${rep.cards.join(" + ")})` : ""}
        </div>
        {rep.description ? (
          <p className="cl-steps">{rep.description}</p>
        ) : (
          <p className="cl-steps">Commander Spellbook lists no steps for this line.</p>
        )}
      </div>
      {rep.prerequisites && (
        <div className="cl-dblock">
          <div className="cl-dh">Prerequisites, from Commander Spellbook</div>
          <p className="cl-steps">{rep.prerequisites}</p>
        </div>
      )}
      {(f.spellPieces.length > 0 || f.medianTurn != null || f.idle > 0) && (
        <div className="cl-dblock cl-dfacts">
          {f.medianTurn != null && (
            <p>
              Together by Forge turn <span className="mono">{f.medianTurn}</span> (median of the games
              it came together; Forge counts every player&apos;s turn).
            </p>
          )}
          {f.idle > 0 && (
            <p>
              Its pieces sat together for <span className="mono">{f.idle}</span>{" "}
              {f.idle === 1 ? "turn" : "turns"} in games the deck did not win. Forge&apos;s AI doesn&apos;t
              run the loop.
            </p>
          )}
          {f.spellPieces.length > 0 && (
            <p>
              {f.spellPieces.join(" / ")} {f.spellPieces.length === 1 ? "is a spell piece" : "are spell pieces"}:
              counted on the turn cast, not from the battlefield.
            </p>
          )}
        </div>
      )}
      {rep.id && (
        <a
          className="bl"
          href={`${SPELLBOOK}${encodeURIComponent(rep.id)}/`}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open on Commander Spellbook
        </a>
      )}
    </div>
  );
}

const COLS = 5;

export function ComboLines({ report }: { report: AnalysisReport | null }) {
  const [openRows, setOpenRows] = useState<Set<string>>(() => new Set());
  const [openFolds, setOpenFolds] = useState<Set<string>>(() => new Set());
  if (!report) return null;
  const decks = Object.entries(report.decks);
  if (!decks.some(([, d]) => d.combos.length > 0 || d.combo_status === "unknown")) return null;

  const toggle = (set: Set<string>, key: string, write: (s: Set<string>) => void) => {
    const next = new Set(set);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    write(next);
  };

  const basis = report.basis ?? "inferred";
  const basisLabel =
    basis === "zone_stream"
      ? "board read from zone records"
      : basis === "mixed"
        ? "board partly read, partly inferred"
        : "board inferred from the event log";

  const idleByDeck = decks
    .map(([name, d]) => ({ name, n: Math.max(0, ...d.combos.map((c) => c.idle_online_turns ?? 0)) }))
    .filter((x) => x.n > 0);

  return (
    <section>
      {report.validity && report.validity.quality !== "clean" && (
        <p className="note">
          <b>
            {report.validity.quality === "polluted"
              ? "These combo figures are not trustworthy."
              : "Read these combo figures with care."}
          </b>{" "}
          {report.validity.reasons.join(" ")}
        </p>
      )}
      <div className="sh">
        <h2>Combo lines (from Commander Spellbook)</h2>
        <span className="meta">{basisLabel}</span>
      </div>
      <p className="sdesc">Forge&apos;s AI doesn&apos;t run combo loops, so these show chances, not results.</p>
      <p className="note only-narrow">Scroll the table sideways for the full breakdown.</p>
      <div className="tblwrap">
        <table className="games cl-table">
          <thead>
            <tr>
              <th scope="col">Combo line</th>
              <th scope="col" className="r">Assembled</th>
              <th scope="col" className="r">Expected from draws</th>
              <th scope="col" className="r">Won after assembling</th>
              <th scope="col">Piece most often missing</th>
            </tr>
          </thead>
          {decks.map(([name, d], di) => {
            const cmdrs = new Set((d.commanders ?? []).map(norm));
            const header = (meta: React.ReactNode) => (
              <tr className="cl-deck">
                <th colSpan={COLS} scope="rowgroup">
                  <span className="cl-sticky">
                    {name}
                    {meta && <span className="cl-deckmeta">{meta}</span>}
                  </span>
                </th>
              </tr>
            );
            if (d.combo_status === "unknown") {
              return (
                <tbody key={name}>
                  {header(null)}
                  <tr>
                    <td colSpan={COLS} className="ctanote">
                      <span className="cl-sticky">
                        Combos unknown: Commander Spellbook was unreachable when this run was analysed.
                      </span>
                    </td>
                  </tr>
                </tbody>
              );
            }
            if (d.combos.length === 0) {
              return (
                <tbody key={name}>
                  {header(null)}
                  <tr>
                    <td colSpan={COLS} className="ctanote">
                      <span className="cl-sticky">
                        Commander Spellbook lists no combos in this deck
                        {d.almost_included > 0 && (
                          <>
                            ; <span className="mono">{d.almost_included}</span> are one card away
                          </>
                        )}
                        .
                      </span>
                    </td>
                  </tr>
                </tbody>
              );
            }
            const fams = familiesOf(d);
            const shown = fams
              .filter((f) => !neverCameTogether(f))
              .sort(
                (a, b) =>
                  b.assembled - a.assembled ||
                  b.won - a.won ||
                  (b.expected ?? -1) - (a.expected ?? -1) ||
                  b.variants.length - a.variants.length,
              );
            const folded = fams
              .filter(neverCameTogether)
              .sort((a, b) => (b.expected ?? 0) - (a.expected ?? 0));
            const foldId = `cl-fold-${di}`;
            const foldOpen = openFolds.has(name);
            const games = fams[0]?.gamesPlayed ?? 0;
            const row = (f: Family, fi: number, group: string) => {
              const rowKey = `${name}\u0001${f.key}`;
              const open = openRows.has(rowKey);
              const detailId = `cl-${group}-${di}-${fi}`;
              return (
                <Fragment key={f.key}>
                  <tr>
                    <td className="cl-line">
                      <LineCell
                        f={f}
                        cmdrs={cmdrs}
                        open={open}
                        controls={detailId}
                        onToggle={() => toggle(openRows, rowKey, setOpenRows)}
                      />
                    </td>
                    <td className="r mono">
                      {f.assembled} of {f.gamesPlayed}
                    </td>
                    <td className="r mono">{fmtExpected(f)}</td>
                    <td className="r mono">{f.assembled > 0 ? f.won : "–"}</td>
                    <td className="cl-miss">
                      {f.missing ? (
                        <>
                          <span className="mono">{f.missing.n}</span> of{" "}
                          <span className="mono">{f.gamesPlayed}</span>: {f.missing.label}
                        </>
                      ) : (
                        "–"
                      )}
                    </td>
                  </tr>
                  {open && (
                    <tr className="cl-detail" id={detailId}>
                      <td colSpan={COLS}>
                        <DetailCell f={f} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            };
            const meta =
              fams.length < d.combos.length
                ? `${plural(d.combos.length, "Spellbook combo")}, grouped into ${plural(fams.length, "row")}`
                : plural(d.combos.length, "Spellbook combo");
            return (
              <Fragment key={name}>
                <tbody>
                  {header(meta)}
                  {shown.map((f, fi) => row(f, fi, "s"))}
                  {folded.length > 0 && (
                    <tr className="cl-foldrow">
                      <td colSpan={COLS}>
                        <div className="cl-sticky">
                          <button
                            type="button"
                            className="cl-toggle"
                            aria-expanded={foldOpen}
                            aria-controls={foldId}
                            onClick={() => toggle(openFolds, name, setOpenFolds)}
                          >
                            {foldOpen
                              ? `Hide the ${plural(folded.length, "line")} that never came together`
                              : `Show ${folded.length}${shown.length > 0 ? " more" : ""} ${
                                  folded.length === 1 ? "line" : "lines"
                                } that never came together`}
                          </button>
                          <span className="ctanote">
                            {" "}
                            (each expected under once in {plural(games, "game")} from draw odds)
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
                {folded.length > 0 && foldOpen && (
                  <tbody id={foldId} className="cl-folded">
                    {folded.map((f, fi) => row(f, fi, "f"))}
                  </tbody>
                )}
              </Fragment>
            );
          })}
        </table>
      </div>
      <p className="note">{report.note}</p>
      <PageDetails label="How these numbers are measured">
        A row is one combo line Commander Spellbook lists for the deck. Variants share a row when
        Spellbook lists the same results for them and they share all but one card; the row counts
        any of them. Assembled counts games in which every piece of at least one variant was on the
        battlefield at once; instant and sorcery pieces count on the turn they were cast. Expected
        from draws is the number of games in which draw odds alone predicted every piece of at least
        one variant would have been drawn by the game&apos;s end, from the cards each deck saw (opening
        hand, one per turn cycle, plus logged effect draws; commanders are always available).
        Assembled above it means tutors did work; far below it means pieces sat in hand or died. Won
        after assembling counts games the deck won after its pieces had been together; the combo need
        not have won them. Lines never together and expected under once in the run fold away, since a
        zero there is the expected outcome.
        {decks.some(([, d]) => d.draws?.per_own_turn != null) && (
          <>
            {" "}Draw velocity:{" "}
            {decks
              .filter(([, d]) => d.draws?.per_own_turn != null)
              .map(([name, d]) => `${name} ${d.draws?.per_own_turn}/turn cycle`)
              .join(" · ")}
            .
          </>
        )}
        {idleByDeck.length > 0 && (
          <>
            {" "}Longest a single line sat together in games its deck did not win:{" "}
            {idleByDeck.map((x) => `${x.name} ${x.n} ${x.n === 1 ? "turn" : "turns"}`).join(" · ")}. Forge&apos;s
            AI does not pilot loops, so treat those decks&apos; numbers as a floor, not a verdict.
          </>
        )}
      </PageDetails>
    </section>
  );
}
