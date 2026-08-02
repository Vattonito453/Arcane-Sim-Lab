"use client";

/** Playtest sandbox — /playtest/[deck]
 *  Solo, rules-free goldfishing (task 08 Part A). The user pilots; the app
 *  moves cards where they are dragged and keeps counts. The three legal
 *  tripwires are deliberately absent and must stay absent:
 *    1. no opponent of any kind;
 *    2. no rules adjudication — no legality checks, no cost payment, no
 *       triggers, no auto-tapping;
 *    3. no win/loss — nothing here ever declares an outcome.
 *  State is ephemeral client state. After the initial deck + card-image
 *  load, the server is never touched. */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Chrome, Footer, PageDetails } from "@/components/Chrome";
import { api } from "@/lib/api";
import { cardFace, loadCards, normalizeName, type CardMap } from "@/lib/cards";
import type { DeckCards } from "@/lib/types";

type ZoneName = "library" | "hand" | "battlefield" | "graveyard" | "exile" | "command";

interface PCard {
  id: string;
  name: string;
  tapped: boolean;
  counters: number;
  token?: boolean;
}

type Zones = Record<ZoneName, PCard[]>;

function shuffled<T>(xs: T[]): T[] {
  // Fisher–Yates; the only randomness in the sandbox.
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function freshZones(deck: DeckCards): Zones {
  const mk = (name: string, i: number, tag: string): PCard => ({
    id: `${tag}-${i}-${name}`,
    name,
    tapped: false,
    counters: 0,
  });
  const library = shuffled(deck.main.map((n, i) => mk(n, i, "m")));
  return {
    library: library.slice(7),
    hand: library.slice(0, 7),
    battlefield: [],
    graveyard: [],
    exile: [],
    command: deck.commanders.map((n, i) => mk(n, i, "c")),
  };
}

export default function PlaytestPage() {
  const params = useParams<{ deck: string }>();
  const deckFile = decodeURIComponent(String(params?.deck ?? ""));

  const [deck, setDeck] = useState<DeckCards | null>(null);
  const [facts, setFacts] = useState<CardMap>({});
  const [err, setErr] = useState<string | null>(null);
  const [zones, setZones] = useState<Zones | null>(null);
  const [life, setLife] = useState(40);
  const [turn, setTurn] = useState(1);
  const [mulls, setMulls] = useState(0);
  const [freeFirst, setFreeFirst] = useState(true);
  const [toBottom, setToBottom] = useState(0);
  const [over, setOver] = useState<ZoneName | null>(null);
  const tokenSeq = useRef(0);

  useEffect(() => {
    let live = true;
    api
      .deck(deckFile)
      .then(async (d) => {
        if (!live) return;
        setDeck(d);
        setZones(freshZones(d));
        // One batched, cached lookup for faces and the lede's figures —
        // the last server contact of the session.
        const map = await loadCards([...d.commanders, ...d.main]);
        if (live) setFacts(map);
      })
      .catch((e: unknown) => live && setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [deckFile]);

  const stats = useMemo(() => {
    if (!deck) return null;
    let lands = 0;
    let mvSum = 0;
    let mvN = 0;
    for (const n of deck.main) {
      const f = facts[normalizeName(n).toLowerCase()];
      if (!f) continue;
      if (f.type_line?.includes("Land") && !f.type_line.includes("Creature")) {
        lands += 1;
      } else if (typeof f.cmc === "number") {
        mvSum += f.cmc;
        mvN += 1;
      }
    }
    return { lands, avgMv: mvN > 0 ? (mvSum / mvN).toFixed(1) : null };
  }, [deck, facts]);

  const move = (id: string, from: ZoneName, to: ZoneName) => {
    setZones((z) => {
      if (!z) return z;
      const card = z[from].find((c) => c.id === id);
      if (!card) return z;
      // Tokens are a physical stand-in; off the battlefield they cease.
      if (card.token && to !== "battlefield") {
        return { ...z, [from]: z[from].filter((c) => c.id !== id) };
      }
      const moved = { ...card, tapped: false };
      return {
        ...z,
        [from]: z[from].filter((c) => c.id !== id),
        [to]: [...z[to], moved], // library drops go to the bottom
      };
    });
    if (from === "hand" && to === "library") setToBottom((n) => Math.max(0, n - 1));
  };

  const draw = (n = 1) => {
    setZones((z) => {
      if (!z) return z;
      const take = z.library.slice(0, n);
      return { ...z, library: z.library.slice(n), hand: [...z.hand, ...take] };
    });
  };

  const nextTurn = () => {
    setZones((z) =>
      z
        ? { ...z, battlefield: z.battlefield.map((c) => ({ ...c, tapped: false })) }
        : z,
    );
    draw(1);
    setTurn((t) => t + 1);
  };

  const mulligan = () => {
    if (!deck) return;
    setZones((z) => {
      if (!z) return z;
      const back = shuffled([...z.library, ...z.hand]);
      return { ...z, library: back.slice(7), hand: back.slice(0, 7) };
    });
    const taken = mulls + 1;
    setMulls(taken);
    setToBottom(Math.max(0, freeFirst ? taken - 1 : taken));
  };

  const reset = () => {
    if (!deck) return;
    setZones(freshZones(deck));
    setLife(40);
    setTurn(1);
    setMulls(0);
    setToBottom(0);
  };

  const addToken = () => {
    tokenSeq.current += 1;
    setZones((z) =>
      z
        ? {
            ...z,
            battlefield: [
              ...z.battlefield,
              { id: `tok-${tokenSeq.current}`, name: "Token", tapped: false, counters: 0, token: true },
            ],
          }
        : z,
    );
  };

  const bump = (zone: ZoneName, id: string, d: number) => {
    setZones((z) =>
      z
        ? {
            ...z,
            [zone]: z[zone].map((c) =>
              c.id === id ? { ...c, counters: Math.max(0, c.counters + d) } : c,
            ),
          }
        : z,
    );
  };

  const tap = (zone: ZoneName, id: string) => {
    if (zone === "command") {
      move(id, "command", "battlefield"); // a zone move, not a rules action
      return;
    }
    if (zone === "hand") {
      move(id, "hand", "battlefield");
      return;
    }
    setZones((z) =>
      z
        ? {
            ...z,
            [zone]: z[zone].map((c) => (c.id === id ? { ...c, tapped: !c.tapped } : c)),
          }
        : z,
    );
  };

  const dropProps = (zone: ZoneName) => ({
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
      setOver(zone);
    },
    onDragLeave: () => setOver((o) => (o === zone ? null : o)),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      setOver(null);
      try {
        const { id, from } = JSON.parse(e.dataTransfer.getData("text/plain"));
        if (id && from && from !== zone) move(id, from as ZoneName, zone);
      } catch {
        /* not one of our drags */
      }
    },
  });

  const card = (c: PCard, zone: ZoneName) => {
    const face = c.token ? null : cardFace(facts[normalizeName(c.name).toLowerCase()]);
    return (
      <div
        key={c.id}
        className={`pt-card${c.tapped ? " tapped" : ""}`}
        draggable
        onDragStart={(e) =>
          e.dataTransfer.setData("text/plain", JSON.stringify({ id: c.id, from: zone }))
        }
        onClick={() => tap(zone, c.id)}
        role="button"
        aria-label={`${c.name}${c.tapped ? ", tapped" : ""}`}
        title={c.name}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- Scryfall hotlink, never rehosted */}
        {face && <img src={face} alt="" loading="lazy" />}
        {(!face || c.token) && <span className="nm">{c.name}</span>}
        {c.counters > 0 && <span className="ctr">{c.counters}</span>}
        <span className="cbtns">
          <button
            aria-label={`Add a counter to ${c.name}`}
            onClick={(e) => {
              e.stopPropagation();
              bump(zone, c.id, 1);
            }}
          >
            +
          </button>
          <button
            aria-label={`Remove a counter from ${c.name}`}
            onClick={(e) => {
              e.stopPropagation();
              bump(zone, c.id, -1);
            }}
          >
            −
          </button>
        </span>
      </div>
    );
  };

  const deckName = deck?.name ?? deckFile.replace(/\.dck$/, "");

  if (err) {
    return (
      <>
        <Chrome />
        <div className="page">
          <div className="head">
            <div>
              <h1>{deckName} — playtest</h1>
              <div className="sub">Could not load this deck</div>
            </div>
          </div>
          <p className="note">{err} — check that the engine API is running, then reload.</p>
        </div>
        <Footer />
      </>
    );
  }

  return (
    <>
      <Chrome />
      <div className="page">
        <Link className="back" href="/playtest">
          ‹ All decks
        </Link>
        <div className="head">
          <div>
            <h1>{deckName} — playtest</h1>
            <div className="sub">
              goldfishing — you pilot everything, nothing here enforces a rule
              <span className="sep">·</span>
              <Link className="bl" href={`/decks/${encodeURIComponent(deckFile)}`}>
                read the decklist
              </Link>
            </div>
          </div>
        </div>

        <p className="lede">
          {deck ? (
            <>
              Drawing from <b>{deckName}</b>&apos;s {deck.main.length}
              {stats && stats.lands > 0 ? (
                <>
                  {" "}— <b>{stats.lands} lands</b>
                  {stats.avgMv && (
                    <>
                      , average mana value <b>{stats.avgMv}</b> outside them
                    </>
                  )}
                </>
              ) : null}
              . Tap a hand or command-zone card to put it onto the battlefield, tap a
              permanent to tap it, and drag cards anywhere else. The app only moves cards
              and keeps count — legality, costs, and triggers are yours to pilot.
            </>
          ) : (
            <>Loading the deck…</>
          )}
        </p>

        <div className="pt-hud">
          <div className="grp">
            <span className="lab">Life</span>
            <button className="pt-mini" aria-label="Lose a life" onClick={() => setLife((l) => l - 1)}>
              −
            </button>
            <span className="val">{life}</span>
            <button className="pt-mini" aria-label="Gain a life" onClick={() => setLife((l) => l + 1)}>
              +
            </button>
          </div>
          <div className="grp">
            <span className="lab">Turn</span>
            <span className="val">{turn}</span>
          </div>
          <button className="btn pri" onClick={nextTurn} disabled={!zones}>
            Next turn — untap all, draw 1
          </button>
          <button className="btn" onClick={mulligan} disabled={!zones}>
            Mulligan
          </button>
          <button className="btn" onClick={addToken} disabled={!zones}>
            Add token
          </button>
          <button className="btn" onClick={reset} disabled={!zones}>
            Reset and reshuffle
          </button>
          <label className="grp">
            <input
              type="checkbox"
              checked={freeFirst}
              onChange={(e) => setFreeFirst(e.target.checked)}
            />
            <span className="lab">free first mulligan (Commander)</span>
          </label>
        </div>

        {toBottom > 0 && (
          <p className="note">
            London mulligan: put <span className="mono">{toBottom}</span>{" "}
            {toBottom === 1 ? "card" : "cards"} on the bottom — drag{" "}
            {toBottom === 1 ? "it" : "them"} from your hand onto the library pile.
          </p>
        )}

        <div className={`pt-zone${over === "battlefield" ? " over" : ""}`} {...dropProps("battlefield")}>
          <span className="zl">Battlefield — click to tap</span>
          {zones?.battlefield.map((c) => card(c, "battlefield"))}
        </div>

        <div className={`pt-zone${over === "hand" ? " over" : ""}`} {...dropProps("hand")}>
          <span className="zl">Hand — click to play</span>
          {zones?.hand.map((c) => card(c, "hand"))}
        </div>

        <div className="pt-row">
          <div className={`pt-zone${over === "command" ? " over" : ""}`} {...dropProps("command")}>
            <span className="zl">Command zone</span>
            {zones?.command.map((c) => card(c, "command"))}
          </div>
          <div className={`pt-zone${over === "graveyard" ? " over" : ""}`} {...dropProps("graveyard")}>
            <span className="zl">Graveyard</span>
            {zones?.graveyard.map((c) => card(c, "graveyard"))}
          </div>
          <div className={`pt-zone${over === "exile" ? " over" : ""}`} {...dropProps("exile")}>
            <span className="zl">Exile</span>
            {zones?.exile.map((c) => card(c, "exile"))}
          </div>
          <div className={`pt-zone${over === "library" ? " over" : ""}`} {...dropProps("library")}>
            <span className="zl">Library</span>
            <div
              className="pt-pile"
              role="button"
              aria-label="Draw a card"
              onClick={() => draw(1)}
            >
              <span className="n">{zones?.library.length ?? "—"}</span>
              <span className="l">tap to draw</span>
              <span className="l">drop to bottom</span>
            </div>
          </div>
        </div>

        <p className="note">
          Everything on this table is ephemeral — reloading the page reshuffles. Nothing is
          adjudicated and nothing declares an outcome; this is a kitchen-table goldfish with
          the counting done for you.
        </p>

        <PageDetails label="Deck details">
          <div>{deckFile}</div>
        </PageDetails>
      </div>
      <Footer />
    </>
  );
}
