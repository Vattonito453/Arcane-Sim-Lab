"use client";

/** The deck gallery, in one place.
 *
 *  It used to live inside /new only, which is why browsing your collection was
 *  a side-effect of configuring a gauntlet. Three pages need it now and they
 *  differ only in what a tile *does*:
 *
 *    /decks     → open the deck              (mode "link")
 *    /playtest  → open the sandbox           (mode "link")
 *    /new       → seat the deck for a run    (mode "select")
 *
 *  In link mode the whole tile is the one action, so there is no second control
 *  competing with it — the "Cards" pill existed only because the tile in select
 *  mode already had a different job.
 *
 *  Commander art is a Scryfall art_crop, hotlinked and never rehosted, resolved
 *  through the engine's cached /cards path by the caller in ONE batched call. */

import Link from "next/link";
import { useMemo, useState } from "react";
import type { DeckEntry } from "@/lib/types";
import { ManaPip, ManaPips } from "@/components/ManaPips";
import { normalizeName, type CardMap } from "@/lib/cards";

const WUBRG = ["W", "U", "B", "R", "G"] as const;
const COLOR_NAME: Record<string, string> = {
  W: "White", U: "Blue", B: "Black", R: "Red", G: "Green",
};

export function factsKey(name: string): string {
  return normalizeName(name).toLowerCase();
}

export function DeckGallery({
  decks,
  facts,
  mode,
  selected = [],
  onToggle,
  hrefFor,
  actionVerb = "Open",
}: {
  decks: DeckEntry[];
  facts: CardMap;
  mode: "link" | "select";
  /** Files, in seat order. Select mode only. */
  selected?: string[];
  onToggle?: (file: string) => void;
  /** Where a tile goes. Link mode only. */
  hrefFor?: (deck: DeckEntry) => string;
  /** Verb used in the tile's accessible name, e.g. "Open" / "Playtest". */
  actionVerb?: string;
}) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Set<string>>(new Set());

  const identityOf = (d: DeckEntry): string[] | null =>
    d.commander ? (facts[factsKey(d.commander)]?.color_identity ?? null) : null;
  const artOf = (d: DeckEntry): string | null =>
    d.commander ? (facts[factsKey(d.commander)]?.art_crop ?? null) : null;

  const toggleFilter = (c: string) =>
    setFilter((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return decks.filter((d) => {
      if (
        needle &&
        !d.name.toLowerCase().includes(needle) &&
        !(d.commander ?? "").toLowerCase().includes(needle)
      ) {
        return false;
      }
      if (filter.size === 0) return true;
      const id = d.commander ? (facts[factsKey(d.commander)]?.color_identity ?? null) : null;
      if (id == null) return true; // unknown identity: never hidden
      if (filter.has("C") && id.length === 0) return true;
      return id.some((c) => filter.has(c.toUpperCase()));
    });
  }, [decks, q, filter, facts]);

  return (
    <>
      <div className="dg-filter">
        <span className="inp dg-search">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            value={q}
            placeholder="Search decks…"
            aria-label="Search decks by name or commander"
            onChange={(e) => setQ(e.target.value)}
          />
        </span>
        <span className="flab">Colour identity</span>
        {WUBRG.map((c) => (
          <label key={c}>
            <input type="checkbox" checked={filter.has(c)} onChange={() => toggleFilter(c)} />
            <ManaPip color={c} />
            {COLOR_NAME[c]}
          </label>
        ))}
        <label>
          <input type="checkbox" checked={filter.has("C")} onChange={() => toggleFilter("C")} />
          <ManaPip color="C" />
          Colorless
        </label>
        <span className="flab dg-count">
          {visible.length === decks.length
            ? `${decks.length} decks`
            : `${visible.length} of ${decks.length}`}
        </span>
      </div>

      <div className="dg">
        {visible.map((d) => {
          const art = artOf(d);
          const identity = identityOf(d);
          const seat = selected.indexOf(d.file);
          // Everything inside the tile except the one action is inert: the
          // scrim is pointer-events:none so the strip where the name sits — and
          // where people naturally click — still hits the action beneath it.
          const face = (
            <>
              {art ? (
                // eslint-disable-next-line @next/next/no-img-element -- Scryfall hotlink, never rehosted
                <img src={art} alt="" loading="lazy" />
              ) : (
                <span className="plate" aria-hidden="true">
                  <span className="k">{d.commander ?? "no commander listed"}</span>
                  {identity && identity.length > 0 && <ManaPips colors={identity} />}
                </span>
              )}
              {seat >= 0 && <span className="seat">P{seat + 1}</span>}
            </>
          );
          return (
            <div key={d.file} className="dg-tile" data-on={seat >= 0 || undefined}>
              {mode === "select" ? (
                <button
                  type="button"
                  className="pick"
                  aria-pressed={seat >= 0}
                  aria-label={`Seat ${d.name}${seat >= 0 ? ` (currently player ${seat + 1})` : ""}`}
                  onClick={() => onToggle?.(d.file)}
                >
                  {face}
                </button>
              ) : (
                <Link
                  className="pick"
                  href={hrefFor ? hrefFor(d) : "#"}
                  aria-label={`${actionVerb} ${d.name}`}
                >
                  {face}
                </Link>
              )}
              <span className="scrim">
                <span className="t">{d.name}</span>
                <ManaPips colors={identity ?? undefined} />
              </span>
            </div>
          );
        })}
      </div>
      {visible.length === 0 && (
        <p className="note">
          No decks match {q.trim() ? `“${q.trim()}”` : "this colour filter"}.
        </p>
      )}
    </>
  );
}
