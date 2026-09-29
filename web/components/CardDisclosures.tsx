"use client";

/** Cards a deck carries that the simulation does not play as written
 *  (repair plan WS11 task 4; the R1.1 disclosure).
 *
 *  Two lists per deck, the same on the run page, the deck page and at import,
 *  all computed by the engine (engine/disclosure.py):
 *    - cards Forge could not load, so every game was played without them;
 *    - cards Forge's AI doesn't cast on its own (scripted AI:RemoveDeck:All).
 *      "Doesn't cast on its own", never "won't play": the owner's wording
 *      (2026-09-27), because Sim Lab's pilot does cast some of them.
 *
 *  Each list is a native <details>: the count is in the summary, and the cards
 *  plus one plain sentence on what it means open beneath it. An empty list is
 *  a static "none" line (nothing to expand); a null list says why it cannot be
 *  checked, never "none". */

import type { DeckDisclosure, RunDisclosures } from "@/lib/types";
import { normalizeName } from "@/lib/cards";

export type DisclosureWhere = "run" | "deck" | "import";
type Kind = "load" | "ai";

const TITLE: Record<Kind, string> = {
  load: "Cards Forge could not load",
  ai: "Cards Forge's AI doesn't cast on its own",
};

/** What the list means for the result, in one plain sentence, which names
 *  the commander when it is on the list. No em dash: this is copy. */
function meaning(kind: Kind, d: DeckDisclosure, where: DisclosureWhere, stock = false): string {
  const cards = (kind === "load" ? d.could_not_load : d.ai_wont_play) ?? [];
  const one = cards.length === 1;
  if (kind === "load") {
    const names = one ? "this name" : "these names";
    if (where === "run") {
      // Index basis: the engine has already dropped any name this run's own
      // log shows in play (engine/disclosure.shown_in_run).
      return d.load_basis === "run"
        ? `Forge left ${one ? "this card" : "these"} out of every game, so this deck played short of its list.`
        : `This run is older than Forge's own load report, so this list comes from Forge's card list today: Forge doesn't know ${names} as written and this run's log never shows ${one ? "it" : "them"}, so ${one ? "it was" : "they were"} most likely left out of every game.`;
    }
    return `Forge doesn't know ${names} as written, so a simulation plays this deck without ${one ? "it" : "them"}; check the spelling, and name a double-faced card by its front face alone.`;
  }
  // Who the sentence is about: the commander alone, the list with the
  // commander on it, or the list.
  const commander = d.commander_ai_wont_play.length > 0;
  const subject = one ? (commander ? "the commander" : "this card") : "these";
  const also = commander && !one ? ", the commander included," : ",";
  // A run Forge's own AI played for every seat had no Sim Lab pilot to cast
  // any of these, so the pilot clause would describe a different run.
  const pilot = where === "run" && stock
    ? "every seat in this run was Forge's own AI, without Sim Lab's pilot."
    : one
      ? "Sim Lab's pilot can still cast it while chasing a combo or tutoring, and work to have the pilot cast such cards is scheduled for November."
      : "Sim Lab's pilot can cast some while chasing a combo or tutoring, and work to have it cast the rest is scheduled for November.";
  return where === "run"
    ? `Forge's AI passes over ${subject} when it picks a spell${also} so a simulation rarely casts ${one ? "it" : "them"} and this result may understate the deck; ${pilot}`
    : `A simulation will rarely cast ${subject}${also} so its result may understate this deck; ${pilot}`;
}

/** A card-name key that meets the engine's lists: printing suffix and set
 *  code dropped, case folded, and a "Front // Back" name met by its front. */
function key(name: string): string {
  return normalizeName(name.split("|")[0]).toLowerCase();
}

function onList(name: string, list: string[] | null | undefined): boolean {
  if (!list?.length) return false;
  const k = key(name);
  const front = k.split(" // ")[0].trim();
  return list.some((c) => {
    const ck = key(c);
    return ck === k || ck === front || ck.split(" // ")[0].trim() === front;
  });
}

/** Which disclosure, if any, names this card: for an inline marker on a
 *  card row. "load" wins, since a card Forge never loads is never cast. */
export function disclosureOf(
  name: string,
  d: DeckDisclosure | null | undefined,
): Kind | null {
  if (!d) return null;
  if (onList(name, d.could_not_load)) return "load";
  if (onList(name, d.ai_wont_play)) return "ai";
  return null;
}

export const INLINE_NOTE: Record<Kind, string> = {
  load: "Forge could not load this card",
  ai: "Forge's AI doesn't cast this on its own",
};

/** One of the two lists for one deck. */
export function DisclosureList({
  kind,
  d,
  where,
  unavailable,
  stock = false,
}: {
  kind: Kind;
  d: DeckDisclosure;
  where: DisclosureWhere;
  /** Why a null list cannot be checked, as a clause ("Forge's card list
   *  isn't on this server yet"). */
  unavailable: string;
  /** A run Forge's own AI played for every seat (pilot kind "stock"). */
  stock?: boolean;
}) {
  const cards = kind === "load" ? d.could_not_load : d.ai_wont_play;
  if (cards == null) {
    return (
      <p className="dsc dsc-static">
        {TITLE[kind]}: not checked. {unavailable}.
      </p>
    );
  }
  if (cards.length === 0) {
    return <p className="dsc dsc-static">{TITLE[kind]}: none.</p>;
  }
  const commander = new Set(d.commander_ai_wont_play);
  return (
    <details className="dsc">
      <summary>
        {/* One span, so the flex summary keeps the space before the count. */}
        <span>
          {TITLE[kind]} (<span className="mono">{cards.length}</span>)
        </span>
      </summary>
      <ul className="dsc-cards">
        {cards.map((c) => (
          <li key={c}>
            {c}
            {kind === "ai" && commander.has(c) && <span className="dsc-role"> (commander)</span>}
          </li>
        ))}
      </ul>
      <p className="dsc-why">{meaning(kind, d, where, stock)}</p>
    </details>
  );
}

/** Both lists for one deck, stacked. */
export function DeckDisclosureRows({
  d,
  where,
  unavailable,
  stock = false,
}: {
  d: DeckDisclosure;
  where: DisclosureWhere;
  unavailable: string;
  stock?: boolean;
}) {
  return (
    <div className="dsc-rows">
      <DisclosureList kind="load" d={d} where={where} unavailable={unavailable} />
      <DisclosureList kind="ai" d={d} where={where} unavailable={unavailable} stock={stock} />
    </div>
  );
}

const NO_INDEX = "Forge's card list isn't on this server yet";
const NO_FILE = "This deck's file is no longer on the server";

/** The run page's section: both lists for every deck in the pod. Renders
 *  nothing for an engine too old to send them. */
export function RunDisclosureSection({
  report,
  name,
  stock = false,
}: {
  report: RunDisclosures | null | undefined;
  /** The deck's one display name (shortName), keyed by its Name=. */
  name: (deck: string) => string;
  /** Forge's own AI played every seat (the run's pilot kind is "stock"). */
  stock?: boolean;
}) {
  if (!report || !report.decks) return null;
  const decks = Object.entries(report.decks);
  if (decks.length === 0) return null;
  const why = report.index ? NO_FILE : NO_INDEX;
  return (
    <section>
      <div className="sh">
        <h2>Cards not played as written</h2>
        <span className="meta">per deck</span>
      </div>
      <p className="sdesc">
        Cards Forge could not load, and cards its AI doesn&apos;t cast on its own. Telemetry
        and coaching never call a card on the second list cold or suggest cutting it.
      </p>
      <div className="dsc-grid">
        {decks.map(([deck, d]) => (
          <div className="dsc-deck" key={deck}>
            <h3>{name(deck)}</h3>
            <DeckDisclosureRows d={d} where="run" unavailable={why} stock={stock} />
          </div>
        ))}
      </div>
    </section>
  );
}

/** The deck page's section. */
export function DeckDisclosureSection({
  d,
}: {
  d: (DeckDisclosure & { index: string | null }) | null | undefined;
}) {
  if (!d) return null;
  return (
    <section>
      <div className="sh">
        <h2>Cards not played as written</h2>
        <span className="meta">read from Forge&apos;s card list</span>
      </div>
      <p className="sdesc">
        What a simulation of this deck leaves out or rarely casts. Telemetry and coaching never
        call a card Forge&apos;s AI doesn&apos;t cast on its own cold, or suggest cutting it.
      </p>
      <DeckDisclosureRows d={d} where="deck" unavailable={NO_INDEX} />
    </section>
  );
}
