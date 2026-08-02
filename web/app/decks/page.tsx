"use client";

/** Decks — /decks
 *
 *  Browsing the collection is a job in its own right. It used to be a
 *  side-effect of configuring a gauntlet: the gallery lived inside /new, and
 *  the only routes to a deck page were a pill on a tile there or an "Open deck"
 *  link inside a hover popover that is display:none below 980px — so on a phone
 *  there was no route at all.
 *
 *  Import is the primary here, which is where it belongs: it is one action
 *  performed on decks, not a peer of Results in the top-level nav. */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";
import { plural } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";
import { DeckGallery } from "@/components/DeckGallery";
import { loadCards, type CardMap } from "@/lib/cards";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";

export default function DecksPage() {
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
        // ONE batched, engine-cached lookup resolves every tile's art and
        // colour identity. Warm cache = zero Scryfall calls.
        const commanders = d.map((x) => x.commander).filter((c): c is string => !!c);
        const map = await loadCards(commanders);
        if (!stop) setFacts({ ...map });
      })
      .catch(() => !stop && setDown(true));
    return () => {
      stop = true;
    };
  }, []);

  const imported = decks?.filter((d) => d.source === "imported").length ?? 0;
  const bundled = (decks?.length ?? 0) - imported;

  return (
    <>
      <Chrome />
      <div className="page">
        <div className="head">
          <div>
            <h1>Decks</h1>
          </div>
          <div className="btns">
            <Link className="btn pri" href="/import">
              Import a deck
            </Link>
          </div>
        </div>

        {down ? (
          <p className="lede">
            The engine at the configured address isn&apos;t answering, so the collection
            can&apos;t be listed. Start it with <span className="mono">{ENGINE_CMD}</span> and
            reload. Nothing here is lost.
          </p>
        ) : !decks ? (
          <p className="lede">Loading the collection…</p>
        ) : decks.length === 0 ? (
          <p className="lede">
            No decks yet.{" "}
            <Link className="bl" href="/import">
              Import one
            </Link>{" "}
            from Moxfield, Archidekt, an MTGO or Arena export, or plain text.
          </p>
        ) : (
          <p className="lede">
            {/* Where a deck came from is bookkeeping, not something anyone
                chooses a deck by, and the three destinations were just the nav
                written out again. */}
            <b>{plural(decks.length, "deck")}</b>. Open one to read every card.
          </p>
        )}

        {decks && decks.length > 0 && (
          <section>
            <DeckGallery decks={decks} facts={facts} mode="link" hrefFor={(d) => `/decks/${encodeURIComponent(d.file)}`} />

          </section>
        )}
      </div>
      <Footer />
    </>
  );
}
