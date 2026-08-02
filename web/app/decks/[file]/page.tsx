"use client";

/** Deck detail — /decks/[file]
 *  The readable view of one deck: every card with its mana cost, type line,
 *  and oracle text, grouped by type, with the commander up top. Facts come
 *  from the engine's cached /cards path in batched calls (Scryfall images
 *  hotlinked, oracle text displayed with attribution, never re-published in
 *  bulk). Imported decks can be deleted from here — inline confirm, no
 *  browser dialogs; bundled decks ship inside the image and refuse. */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Chrome, Footer } from "@/components/Chrome";
import { api } from "@/lib/api";
import { ManaPips } from "@/components/ManaPips";
import {
  cardFace, KIND_LABEL, KIND_ORDER, kindOf, loadCards, normalizeName,
  type CardFacts, type CardMap, type Kind,
} from "@/lib/cards";
import type { DeckCards } from "@/lib/types";

function factsKey(name: string): string {
  return normalizeName(name).toLowerCase();
}

function CardRow({ name, qty, facts }: { name: string; qty: number; facts?: CardFacts }) {
  const face = cardFace(facts);
  return (
    <div className="card-row">
      {face ? (
        // eslint-disable-next-line @next/next/no-img-element -- Scryfall hotlink, never rehosted
        <img src={face} alt="" loading="lazy" />
      ) : (
        <span className="noart" aria-hidden="true" />
      )}
      <div className="cr-b">
        <div className="cr-n">
          {name}
          {qty > 1 && <span className="qty">×{qty}</span>}
          {facts?.mana_cost && <span className="cost">{facts.mana_cost}</span>}
        </div>
        <div className="cr-t">
          {facts?.type_line ?? "type unresolved — not in the card cache yet"}
          {facts?.power != null && facts?.toughness != null && (
            <> · {facts.power}/{facts.toughness}</>
          )}
        </div>
        {facts?.oracle_text && <div className="cr-o">{facts.oracle_text}</div>}
      </div>
    </div>
  );
}

export default function DeckPage() {
  const params = useParams<{ file: string }>();
  const router = useRouter();
  const file = decodeURIComponent(String(params?.file ?? ""));

  const [deck, setDeck] = useState<DeckCards | null>(null);
  const [facts, setFacts] = useState<CardMap>({});
  const [err, setErr] = useState<string | null>(null);
  const [armed, setArmed] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .deck(file)
      .then(async (d) => {
        if (!live) return;
        setDeck(d);
        const map = await loadCards([...d.commanders, ...d.main]);
        if (live) setFacts({ ...map });
      })
      .catch((e: unknown) => live && setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [file]);

  const view = useMemo(() => {
    if (!deck) return null;
    const counts = new Map<string, number>();
    for (const n of deck.main) counts.set(n, (counts.get(n) ?? 0) + 1);
    const byKind = new Map<Kind, { name: string; qty: number }[]>();
    let lands = 0;
    let mvSum = 0;
    let mvN = 0;
    for (const [name, qty] of counts) {
      const f = facts[factsKey(name)];
      const k = kindOf(name, f);
      const arr = byKind.get(k) ?? [];
      arr.push({ name, qty });
      byKind.set(k, arr);
      if (f?.type_line?.includes("Land") && !f.type_line.includes("Creature")) {
        lands += qty;
      } else if (typeof f?.cmc === "number") {
        mvSum += f.cmc * qty;
        mvN += qty;
      }
    }
    for (const arr of byKind.values()) arr.sort((a, b) => a.name.localeCompare(b.name));
    const identity = deck.commanders.length
      ? facts[factsKey(deck.commanders[0])]?.color_identity
      : undefined;
    return {
      byKind,
      lands,
      avgMv: mvN > 0 ? (mvSum / mvN).toFixed(1) : null,
      identity,
      unique: counts.size,
    };
  }, [deck, facts]);

  const doDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    setDelErr(null);
    try {
      const r = await api.deleteDeck(file);
      if (!r.ok) throw new Error(r.error ?? "the engine refused the delete");
      router.push("/new");
    } catch (e: unknown) {
      setDelErr(e instanceof Error ? e.message : String(e));
      setDeleting(false);
      setArmed(false);
    }
  };

  const name = deck?.name ?? file.replace(/\.dck$/, "");
  const enc = encodeURIComponent(file);

  if (err) {
    return (
      <>
        <Chrome context="Deck" />
        <div className="page">
          <div className="head">
            <div>
              <h1>{name}</h1>
              <div className="sub">Could not load this deck</div>
            </div>
          </div>
          <p className="note">{err} — check that the engine API is running, then reload.</p>
        </div>
        <Footer right={file} />
      </>
    );
  }

  return (
    <>
      <Chrome context={name} />
      <div className="page">
        <div className="head">
          <div>
            <h1>{name}</h1>
            <div className="sub">
              <span className="mono">{file}</span>
              {deck && (
                <>
                  <span className="sep">·</span>
                  {deck.commanders.join(" · ") || "no commander"}
                  <span className="sep">·</span>
                  <span className="mono">{deck.main.length}</span> cards
                  <span className="sep">·</span>
                  {deck.source ?? "…"}
                </>
              )}
              {view?.identity && (
                <>
                  <span className="sep">·</span>
                  <ManaPips colors={view.identity} />
                </>
              )}
            </div>
          </div>
          <div className="btns">
            <Link className="btn pri" href={`/new?deck=${enc}`}>
              Use in a run
            </Link>
            <Link className="btn" href={`/playtest/${enc}`}>
              Playtest
            </Link>
            {deck?.source === "imported" && !armed && (
              <button className="btn" onClick={() => setArmed(true)}>
                Delete deck
              </button>
            )}
            {deck?.source === "imported" && armed && (
              <>
                <button className="btn" onClick={() => void doDelete()} aria-disabled={deleting}>
                  {deleting ? "Deleting…" : "Delete permanently — cannot be undone"}
                </button>
                <a
                  className="q"
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    setArmed(false);
                  }}
                >
                  Keep it
                </a>
              </>
            )}
          </div>
        </div>

        {delErr && (
          <p className="note">
            <span className="st bad">
              <i />
              Couldn&apos;t delete
            </span>{" "}
            {delErr}
          </p>
        )}

        <p className="lede">
          {deck && view ? (
            <>
              <b>{deck.main.length} cards</b>, {view.unique} distinct
              {view.lands > 0 && (
                <>
                  {" "}— <b>{view.lands} lands</b>
                  {view.avgMv && (
                    <>
                      , average mana value <b>{view.avgMv}</b> outside them
                    </>
                  )}
                </>
              )}
              .{" "}
              {deck.source === "bundled"
                ? "This deck ships with the engine and cannot be deleted."
                : "Imported — it can be deleted from here."}
            </>
          ) : (
            <>Loading the deck…</>
          )}
        </p>

        {deck && deck.commanders.length > 0 && (
          <section>
            <div className="sh">
              <h2>Commander</h2>
            </div>
            {deck.commanders.map((c) => (
              <CardRow key={c} name={c} qty={1} facts={facts[factsKey(c)]} />
            ))}
          </section>
        )}

        {view &&
          KIND_ORDER.filter((k) => view.byKind.has(k)).map((k) => (
            <section key={k}>
              <div className="sh">
                <h2>{KIND_LABEL[k]}</h2>
                <span className="meta">
                  {view.byKind.get(k)!.reduce((a, r) => a + r.qty, 0)} cards
                </span>
              </div>
              {view.byKind.get(k)!.map((r) => (
                <CardRow key={r.name} name={r.name} qty={r.qty} facts={facts[factsKey(r.name)]} />
              ))}
            </section>
          ))}

        <p className="note">
          Card text and images via Scryfall, © Wizards of the Coast — shown for reference.
          Cards the cache hasn&apos;t resolved yet group under Unidentified and fill in as
          facts arrive.
        </p>
      </div>
      <Footer right={file} />
    </>
  );
}
