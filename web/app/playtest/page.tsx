"use client";

/** Playtest — /playtest
 *
 *  The sandbox's front door. It had none: /playtest/[deck] was reachable only
 *  from a button on a deck page, or from a hover popover that doesn't exist
 *  below 980px.
 *
 *  The lede states the carve-out in the product's own voice, because this page
 *  now advertises the mode from the nav. Per CLAUDE.md the tripwires that would
 *  make this a gameplay client are an opponent of any kind, rules adjudication
 *  by the app, or a declared win/loss — none of which this has. */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";
import { plural } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";
import { DeckGallery } from "@/components/DeckGallery";
import { loadCards, type CardMap } from "@/lib/cards";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";

export default function PlaytestIndexPage() {
  const [decks, setDecks] = useState<DeckEntry[] | null>(null);
  const [facts, setFacts] = useState<CardMap>({});
  const [down, setDown] = useState(false);

  useEffect(() => {
    let stop = false;
    api
      .decks()
      .then(async (d) => {
        if (stop) return;
        setDecks(d);
        const commanders = d.map((x) => x.commander).filter((c): c is string => !!c);
        const map = await loadCards(commanders);
        if (!stop) setFacts({ ...map });
      })
      .catch(() => !stop && setDown(true));
    return () => {
      stop = true;
    };
  }, []);

  return (
    <>
      <Chrome />
      <div className="page">
        <h1>Playtest</h1>

        {down ? (
          <p className="lede">
            The engine at the configured address isn&apos;t answering, so decks can&apos;t be
            listed. Start it with <span className="mono">{ENGINE_CMD}</span> and reload.
          </p>
        ) : (
          <p className="lede">
            Goldfish a deck on your own: draw, mulligan, drag cards between zones, keep counters.
            The app moves cards and keeps count; <b>nothing here enforces a rule</b>. There is no
            opponent and no outcome is declared.
          </p>
        )}

        {decks && decks.length === 0 && (
          <p className="note">
            No decks yet.{" "}
            <Link className="bl" href="/import">
              Import one
            </Link>{" "}
            and it appears here.
          </p>
        )}

        {decks && decks.length > 0 && (
          <section>
            <div className="sh">
              <h2>Choose a deck</h2>
              <span className="meta">{plural(decks.length, "deck")}</span>
            </div>
            <DeckGallery
              decks={decks}
              facts={facts}
              mode="link"
              actionVerb="Playtest"
              hrefFor={(d) => `/playtest/${encodeURIComponent(d.file)}`}
            />
            <p className="note">
              Everything on the table is ephemeral; reloading reshuffles. Nothing is adjudicated
              and nothing declares a winner; this is a kitchen-table goldfish with the counting
              done for you.
            </p>
          </section>
        )}

        {!decks && !down && <p className="note">Loading decks…</p>}
      </div>
      <Footer />
    </>
  );
}
