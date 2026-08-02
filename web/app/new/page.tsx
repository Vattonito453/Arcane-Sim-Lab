"use client";

/** New run — /new
 *  The deck picker, rebuilt as an art gallery (task 12). Each deck is a tile
 *  showing its commander's Scryfall art_crop (hotlinked, resolved through the
 *  engine's cached /cards path in ONE batched call) with the name on a scrim.
 *  Selection is the cyan interaction treatment; the single primary lives in
 *  the right rail with the games select and the runtime estimate. Hovering or
 *  keyboard-focusing a tile surfaces the decklist in a fixed popover layer
 *  (Escape dismisses). The ?deck= param preselects (import links here). */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { DeckCards, DeckEntry } from "@/lib/types";
import { estimateSeconds, fmtDuration, plural } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";
import { ManaPip, ManaPips } from "@/components/ManaPips";
import {
  KIND_LABEL, KIND_ORDER, kindOf, loadCards, normalizeName,
  type CardMap, type Kind,
} from "@/lib/cards";
import ApiBaseSetting from "@/components/ApiBaseSetting";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";
const WUBRG = ["W", "U", "B", "R", "G"] as const;
const COLOR_NAME: Record<string, string> = {
  W: "White", U: "Blue", B: "Black", R: "Red", G: "Green",
};

interface Health {
  rules: number;
  keywords: number;
  glossary_terms: number;
}

function factsKey(name: string): string {
  return normalizeName(name).toLowerCase();
}

/** Decklist popover content: contents grouped by type where card facts are
 *  cached; unknown types group honestly under "Unidentified". */
function DeckListPop({
  deck, contents, facts, x, y, onClose,
}: {
  deck: DeckEntry;
  contents: DeckCards | null;
  facts: CardMap;
  /** Computed anchor beside the opening tile — see openPop(). */
  x: number;
  y: number;
  onClose: () => void;
}) {
  const groups = useMemo(() => {
    if (!contents) return null;
    const counts = new Map<string, number>();
    for (const n of contents.main) counts.set(n, (counts.get(n) ?? 0) + 1);
    const byKind = new Map<Kind, { name: string; count: number }[]>();
    for (const [name, count] of counts) {
      const k = kindOf(name, facts[factsKey(name)]);
      const arr = byKind.get(k) ?? [];
      arr.push({ name, count });
      byKind.set(k, arr);
    }
    for (const arr of byKind.values()) arr.sort((a, b) => a.name.localeCompare(b.name));
    return byKind;
  }, [contents, facts]);

  // Portaled to <body>: our glass panels carry backdrop-filter, and a
  // filtered ancestor captures position:fixed in some browsers — the popover
  // then pins to the top of the DOCUMENT and scrolls out of view. On body
  // there is no ancestor to capture it, so fixed means the viewport
  // everywhere.
  return createPortal(
    <div
      className="glass-panel dl-pop"
      role="dialog"
      aria-label={`Decklist: ${deck.name}`}
      // Computed anchor position — the "computed values" inline-style
      // exemption; everything else lives in globals.css.
      style={{ left: x, top: y }}
      onMouseLeave={onClose}
    >
      <h3>{deck.name}</h3>
      <div className="row">
        <span>
          {contents ? `${contents.main.length} cards` : "loading decklist…"}
        </span>
        <a
          className="q"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            onClose();
          }}
        >
          Close (Esc)
        </a>
      </div>
      {contents && contents.commanders.length > 0 && (
        <>
          <div className="grp-h">Commander</div>
          {contents.commanders.map((c) => (
            <div key={c} className="row">
              <span>{c}</span>
            </div>
          ))}
        </>
      )}
      {groups &&
        KIND_ORDER.filter((k) => groups.has(k)).map((k) => (
          <div key={k}>
            <div className="grp-h">
              {KIND_LABEL[k]} · {groups.get(k)!.reduce((a, r) => a + r.count, 0)}
            </div>
            {groups.get(k)!.map((r) => (
              <div key={r.name} className="row">
                <span>{r.name}</span>
                <span className="n">{r.count}</span>
              </div>
            ))}
          </div>
        ))}
      <div className="grp-h">
        <Link className="bl" href={`/decks/${encodeURIComponent(deck.file)}`}>
          Open deck →
        </Link>
        {"  "}
        <Link className="bl" href={`/playtest/${encodeURIComponent(deck.file)}`}>
          Playtest →
        </Link>
      </div>
    </div>,
    document.body,
  );
}

function NewRunInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselect = searchParams.get("deck");

  const [decks, setDecks] = useState<DeckEntry[] | null>(null);
  const [facts, setFacts] = useState<CardMap>({});
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  const [healthErr, setHealthErr] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [selected, setSelected] = useState<string[]>([]);
  const [filter, setFilter] = useState<Set<string>>(new Set());
  // Popover anchor: the inspected deck plus a computed fixed position beside
  // its tile. Anchoring beside the tile (not a fixed slot) is load-bearing:
  // a popover that can appear under the cursor unmounts itself in a
  // mouseenter/mouseleave loop and flickers.
  const [inspect, setInspect] = useState<{ file: string; x: number; y: number } | null>(null);
  const [contents, setContents] = useState<Record<string, DeckCards>>({});
  const [games, setGames] = useState(16);
  const [starting, setStarting] = useState(false);
  const [startErr, setStartErr] = useState<string | null>(null);
  const appliedPreselect = useRef(false);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let stop = false;
    setDown(false);
    setHealthErr(false);
    api
      .health()
      .then((h) => !stop && setHealth(h))
      .catch(() => {
        if (!stop) {
          setHealth(null);
          setHealthErr(true);
        }
      });
    api
      .decks()
      .then(async (d) => {
        if (stop) return;
        setDecks(d);
        // ONE batched, engine-cached lookup resolves every tile's art and
        // color identity. Warm cache = zero Scryfall calls.
        const commanders = d.map((x) => x.commander).filter((c): c is string => !!c);
        const map = await loadCards(commanders);
        if (!stop) setFacts({ ...map });
      })
      .catch(() => {
        if (!stop) {
          setDecks(null);
          setDown(true);
        }
      });
    return () => {
      stop = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (appliedPreselect.current || !preselect || !decks) return;
    if (decks.some((d) => d.file === preselect)) {
      appliedPreselect.current = true;
      setSelected((prev) =>
        prev.includes(preselect) || prev.length >= 4 ? prev : [...prev, preselect]
      );
    }
  }, [preselect, decks]);

  /** Anchor the popover beside a tile: to its right, flipping left when the
   *  viewport edge is near, top aligned with the tile but pushed up just
   *  enough that the panel's max height always fits the viewport. */
  const openPop = (file: string, el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    let x = r.right + 12;
    if (x + 312 > window.innerWidth) x = r.left - 312;
    x = Math.max(8, x);
    const maxH = Math.min(window.innerHeight * 0.56, 560); // mirrors .dl-pop max-height
    const y = Math.max(8, Math.min(r.top - 8, window.innerHeight - maxH - 16));
    setInspect({ file, x, y });
  };

  // Fetch decklist contents lazily, once per inspected deck.
  const inspectFile = inspect?.file ?? null;
  useEffect(() => {
    if (!inspectFile || contents[inspectFile]) return;
    let stop = false;
    api
      .deck(inspectFile)
      .then(async (dc) => {
        if (stop) return;
        setContents((prev) => ({ ...prev, [inspectFile]: dc }));
        // Facts for type grouping — batched and memoized; repeat inspections
        // of the same deck cost nothing.
        const map = await loadCards([...dc.commanders, ...dc.main]);
        if (!stop) setFacts({ ...map });
      })
      .catch(() => {});
    return () => {
      stop = true;
    };
  }, [inspectFile, contents]);

  // Escape dismisses the popover from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setInspect(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const toggle = (file: string) => {
    setStartErr(null);
    setSelected((prev) => {
      if (prev.includes(file)) return prev.filter((f) => f !== file);
      if (prev.length >= 4) return prev;
      return [...prev, file];
    });
  };

  const toggleFilter = (c: string) => {
    setFilter((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  };

  const identityOf = useCallback(
    (d: DeckEntry): string[] | null => {
      if (!d.commander) return null;
      const f = facts[factsKey(d.commander)];
      return f?.color_identity ?? null;
    },
    [facts],
  );

  const visible = useMemo(() => {
    if (!decks) return [];
    if (filter.size === 0) return decks;
    return decks.filter((d) => {
      const id = identityOf(d);
      if (id == null) return true; // unknown identity: never hidden
      if (filter.has("C") && id.length === 0) return true;
      return id.some((c) => filter.has(c.toUpperCase()));
    });
  }, [decks, filter, identityOf]);

  const canRun = selected.length >= 2 && selected.length <= 4;
  const selectedDecks = selected
    .map((f) => decks?.find((d) => d.file === f))
    .filter((d): d is DeckEntry => !!d);

  const start = async () => {
    if (!canRun || starting) return;
    setStarting(true);
    setStartErr(null);
    try {
      const r = await api.simulate(selected, games);
      if (!r.ok || !r.job_id) throw new Error("The engine refused the run — is another simulation in progress?");
      router.push(`/runs/${encodeURIComponent(r.job_id)}`);
    } catch (e) {
      setStartErr(e instanceof Error ? e.message : String(e));
      setStarting(false);
    }
  };

  const artOf = (d: DeckEntry): string | null =>
    d.commander ? (facts[factsKey(d.commander)]?.art_crop ?? null) : null;

  const inspectDeck = inspect ? decks?.find((d) => d.file === inspect.file) : undefined;

  return (
    <>
      <Chrome context="New run" />
      <div className="page">
        <h1>New run</h1>

        {down ? (
          <p className="lede">
            The engine at the configured address isn&apos;t answering. Start it with{" "}
            <span className="mono">{ENGINE_CMD}</span> and retry — nothing here is lost.
          </p>
        ) : !decks ? (
          <p className="lede">Loading decks…</p>
        ) : (
          <p className="lede">
            <b>{decks.length} decks</b> on this engine. Click a tile to seat it, or{" "}
            <b>Cards</b> to read the whole decklist. Pick two to four and run a gauntlet —
            results land under <Link className="bl" href="/results">Results</Link>.
          </p>
        )}

        {down ? (
          <p className="note">
            <span className="st bad">
              <i />
              Engine unreachable
            </span>{" "}
            — is <span className="mono">{ENGINE_CMD}</span> running?{" "}
            <a
              className="q"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                reload();
              }}
            >
              Retry
            </a>
          </p>
        ) : !decks ? (
          <p className="note">Loading decks…</p>
        ) : decks.length === 0 ? (
          <p className="note">
            No decks on this engine yet —{" "}
            <Link className="bl" href="/import">
              import one
            </Link>{" "}
            to get started.
          </p>
        ) : (
          <div className="stage">
            <div>
              <section>
                <div className="sh">
                  <h2>Pick decks</h2>
                  <span className="meta">
                    {visible.length} of {plural(decks.length, "deck")}
                  </span>
                  <span className="right">
                    <ApiBaseSetting onChanged={reload} />
                    <span className="meta"> · </span>
                    {health ? (
                      <span className="meta">
                        <span className="mono">{health.rules.toLocaleString("en-US")}</span> rules loaded
                      </span>
                    ) : healthErr ? (
                      <span className="st bad">
                        <i />
                        Engine unreachable
                      </span>
                    ) : (
                      <span className="meta">checking engine…</span>
                    )}
                    <span className="meta"> · </span>
                    <Link className="bl" href="/import">
                      Import a deck →
                    </Link>
                  </span>
                </div>

                <div className="dg-filter">
                  <span className="flab">Filter by color identity</span>
                  {WUBRG.map((c) => (
                    <label key={c}>
                      <input
                        type="checkbox"
                        checked={filter.has(c)}
                        onChange={() => toggleFilter(c)}
                      />
                      <ManaPip color={c} />
                      {COLOR_NAME[c]}
                    </label>
                  ))}
                  <label>
                    <input
                      type="checkbox"
                      checked={filter.has("C")}
                      onChange={() => toggleFilter("C")}
                    />
                    Colorless
                  </label>
                </div>

                <div
                  className="dg"
                  onMouseLeave={(e) => {
                    // Moving INTO the popover must not dismiss it — that is
                    // how it stays hoverable (and scrollable) without a
                    // dismiss/re-open flicker at the boundary.
                    const to = e.relatedTarget;
                    if (to instanceof Node && document.querySelector(".dl-pop")?.contains(to)) return;
                    setInspect(null);
                  }}
                >
                  {visible.map((d) => {
                    const seat = selected.indexOf(d.file);
                    const art = artOf(d);
                    return (
                      // Two actions per tile, so both get a real control: the
                      // full-bleed button seats the deck for a run, and a
                      // labeled "Cards" button opens the deck page. The
                      // second action used to be bare text in the scrim —
                      // invisible, so nobody found it.
                      <div
                        key={d.file}
                        className="dg-tile"
                        data-on={seat >= 0 || undefined}
                        onMouseEnter={(e) => openPop(d.file, e.currentTarget)}
                      >
                        <button
                          type="button"
                          className="pick"
                          aria-pressed={seat >= 0}
                          aria-label={`Seat ${d.name}${seat >= 0 ? ` (currently player ${seat + 1})` : ""}`}
                          onClick={() => toggle(d.file)}
                          onFocus={(e) => openPop(d.file, e.currentTarget)}
                        >
                          {art && (
                            // eslint-disable-next-line @next/next/no-img-element -- Scryfall hotlink, never rehosted
                            <img src={art} alt="" loading="lazy" />
                          )}
                          {seat >= 0 && <span className="seat">P{seat + 1}</span>}
                        </button>
                        <Link
                          className="dg-view"
                          href={`/decks/${encodeURIComponent(d.file)}`}
                          aria-label={`Read every card in ${d.name}`}
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                               stroke="currentColor" strokeWidth="2" strokeLinecap="round"
                               strokeLinejoin="round" aria-hidden="true">
                            <path d="M4 5h7a2 2 0 0 1 2 2v12a1.5 1.5 0 0 0-1.5-1.5H4Z" />
                            <path d="M20 5h-7a2 2 0 0 0-2 2v12a1.5 1.5 0 0 1 1.5-1.5H20Z" />
                          </svg>
                          Cards
                        </Link>
                        <span className="scrim">
                          <span className="t">{d.name}</span>
                          <ManaPips colors={identityOf(d) ?? undefined} />
                        </span>
                      </div>
                    );
                  })}
                  {visible.length === 0 && (
                    <p className="note">No decks match this color filter.</p>
                  )}
                </div>
                <p className="note">
                  Commander art via Scryfall, resolved through the engine&apos;s card cache in
                  one batched call. A deck with no commander (or unresolved art) shows a
                  name-only tile.
                </p>
              </section>
            </div>

            <div>
              <section>
                <div className="sh">
                  <h2>Selected decks</h2>
                  <span className="meta">{selected.length} of 2–4</span>
                </div>
                {selectedDecks.length === 0 && (
                  <p className="note">Click tiles to seat decks — order here is seat order.</p>
                )}
                {selectedDecks.map((d, i) => {
                  const art = artOf(d);
                  return (
                    <div className="rail-deck" key={d.file}>
                      {art ? (
                        // eslint-disable-next-line @next/next/no-img-element -- Scryfall hotlink
                        <img src={art} alt="" />
                      ) : (
                        <span className="noart" aria-hidden="true" />
                      )}
                      <span className="t">
                        <span className="mono">P{i + 1}</span>{" "}
                        <Link className="bl" href={`/decks/${encodeURIComponent(d.file)}`}>
                          {d.name}
                        </Link>
                        <small>{d.commander ?? d.file}</small>
                      </span>
                      <a
                        className="q"
                        href="#"
                        aria-label={`Remove ${d.name}`}
                        onClick={(e) => {
                          e.preventDefault();
                          toggle(d.file);
                        }}
                      >
                        Remove
                      </a>
                    </div>
                  );
                })}

                <div className="ctarow">
                  <span className="ctanote">Games</span>
                  <select
                    className="sel"
                    value={games}
                    aria-label="Games to simulate"
                    onChange={(e) => setGames(Number(e.target.value))}
                  >
                    <option value={1}>1 game</option>
                    <option value={2}>2 games</option>
                    <option value={8}>8 games</option>
                    <option value={16}>16 games</option>
                    <option value={32}>32 games</option>
                  </select>
                </div>
                <div className="ctarow">
                  {/* The primary stays live (DESIGN_SYSTEM.md §6): when the run
                      can't start, the blocker is stated beside it instead. */}
                  <button
                    className="btn pri"
                    aria-disabled={!canRun || starting}
                    aria-describedby={!canRun ? "run-blocker" : undefined}
                    onClick={() => void start()}
                  >
                    {starting ? "Starting run…" : `Run ${plural(games, "game")}`}
                  </button>
                </div>
                {!canRun && (
                  <p className="ctanote" id="run-blocker">
                    Pick at least 2 decks — you have {selected.length}.
                  </p>
                )}
                {canRun && (
                  // Shown before you commit, because the cost is driven by pod
                  // size far more than by game count: four decks is ~20x the
                  // per-game time of two.
                  <p className="ctanote">
                    about <span className="mono">{fmtDuration(estimateSeconds(games, selected.length))}</span>
                    {games === 1 ? " — you can watch this one play out" : ""}
                  </p>
                )}
                {startErr && (
                  <p className="note">
                    <span className="st bad">
                      <i />
                      Couldn&apos;t start
                    </span>{" "}
                    {startErr}
                  </p>
                )}
              </section>
            </div>
          </div>
        )}

        {inspectDeck && inspect && (
          <DeckListPop
            deck={inspectDeck}
            contents={contents[inspectDeck.file] ?? null}
            facts={facts}
            x={inspect.x}
            y={inspect.y}
            onClose={() => setInspect(null)}
          />
        )}
      </div>
      <Footer
        right={
          health
            ? `${health.rules.toLocaleString("en-US")} rules · ${health.keywords} keywords`
            : undefined
        }
      />
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <NewRunInner />
    </Suspense>
  );
}
