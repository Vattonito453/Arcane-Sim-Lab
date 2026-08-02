"use client";

/** Simulate — /new
 *
 *  Seat two to four decks and run a gauntlet. That is the only job on this page
 *  now. It used to also be the deck browser, which is why a tile needed two
 *  controls — a full-bleed "seat" button plus a "Cards" pill for reading the
 *  list — and why a hover popover was carrying the routes to the deck page and
 *  the sandbox. Browsing moved to /decks and the sandbox to /playtest, so a
 *  tile here has exactly one action and no hover-only affordance survives.
 *
 *  The engine address and the rules count used to sit in this page's section
 *  header. They are infrastructure, not part of picking decks; the address is a
 *  real setting and lives once, in the nav sheet.
 *
 *  ?deck= preselects (import links here). */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";
import { estimateSeconds, fmtDuration, plural } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";
import { DeckGallery, factsKey } from "@/components/DeckGallery";
import { loadCards, type CardMap } from "@/lib/cards";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";

function NewRunInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselect = searchParams.get("deck");

  const [decks, setDecks] = useState<DeckEntry[] | null>(null);
  const [facts, setFacts] = useState<CardMap>({});
  const [down, setDown] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [selected, setSelected] = useState<string[]>([]);
  const [games, setGames] = useState(16);
  const [starting, setStarting] = useState(false);
  const [startErr, setStartErr] = useState<string | null>(null);
  const appliedPreselect = useRef(false);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let stop = false;
    setDown(false);
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
        prev.includes(preselect) || prev.length >= 4 ? prev : [...prev, preselect],
      );
    }
  }, [preselect, decks]);

  const toggle = (file: string) => {
    setStartErr(null);
    setSelected((prev) => {
      if (prev.includes(file)) return prev.filter((f) => f !== file);
      if (prev.length >= 4) return prev;
      return [...prev, file];
    });
  };

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
      if (!r.ok || !r.job_id)
        throw new Error("The engine refused the run. Is another simulation in progress?");
      router.push(`/runs/${encodeURIComponent(r.job_id)}`);
    } catch (e) {
      setStartErr(e instanceof Error ? e.message : String(e));
      setStarting(false);
    }
  };

  const artOf = (d: DeckEntry): string | null =>
    d.commander ? (facts[factsKey(d.commander)]?.art_crop ?? null) : null;

  const gamesSelect = (
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
  );

  return (
    <>
      <Chrome />
      <div className="page">
        <h1>Simulate</h1>

        {down ? (
          <p className="lede">
            The engine at the configured address isn&apos;t answering. Start it with{" "}
            <span className="mono">{ENGINE_CMD}</span> and retry. Nothing here is lost.
          </p>
        ) : !decks ? (
          <p className="lede">Loading decks…</p>
        ) : (
          <p className="lede">
            Tap two to four decks to seat them, then run the gauntlet.
          </p>
        )}

        {down ? (
          <p className="note">
            <span className="st bad">
              <i />
              Engine unreachable
            </span>{": "}
            is <span className="mono">{ENGINE_CMD}</span> running?{" "}
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
            No decks on this engine yet.{" "}
            <Link className="bl" href="/import">
              Import one
            </Link>{" "}
            to get started.
          </p>
        ) : (
          <div className="stage">
            <div>
              <section>
                <div className="sh">
                  <h2>Pick decks</h2>
                </div>
                <DeckGallery
                  decks={decks}
                  facts={facts}
                  mode="select"
                  selected={selected}
                  onToggle={toggle}
                />

              </section>
            </div>

            <div>
              <section>
                <div className="sh">
                  <h2>Selected decks</h2>
                  <span className="meta">{selected.length} of 2–4</span>
                </div>
                {selectedDecks.length === 0 && (
                  <p className="note">Seat order is the order you pick.</p>
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
                        <small>{d.commander ?? "no commander listed"}</small>
                      </span>
                      <button
                        type="button"
                        className="rail-x"
                        aria-label={`Remove ${d.name}`}
                        onClick={() => toggle(d.file)}
                      >
                        Remove
                      </button>
                    </div>
                  );
                })}

                {/* Wide screens keep the action in the rail. Below 980px this
                    block hides and the sticky bar below takes over, because the
                    rail stacks after twenty-nine tiles. */}
                <div className="rail-cta">
                  <div className="ctarow">
                    <span className="ctanote">Games</span>
                    {gamesSelect}
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
                      Pick at least 2 decks; you have {selected.length}.
                    </p>
                  )}
                  {canRun && (
                    // Shown before you commit, because the cost is driven by pod
                    // size far more than by game count: four decks is ~20x the
                    // per-game time of two.
                    <p className="ctanote">
                      about{" "}
                      <span className="mono">
                        {fmtDuration(estimateSeconds(games, selected.length))}
                      </span>
                      {games === 1 ? ", so you can watch this one play out" : ""}
                    </p>
                  )}
                </div>

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

        {/* Narrow screens: the action follows you down the gallery instead of
            waiting ~7,000px below it. */}
        {decks && decks.length > 0 && (
          <div className="runbar">
            <span className="cnt">
              {canRun ? (
                <>
                  <b>{selected.length}</b> seated ·{" "}
                  <span className="mono">
                    {fmtDuration(estimateSeconds(games, selected.length))}
                  </span>
                  <small>{selectedDecks.map((d) => d.name).join(" · ")}</small>
                </>
              ) : (
                <>
                  <b>{selected.length}</b> of 2–4 seated
                  <small>Pick at least 2 to run</small>
                </>
              )}
            </span>
            {gamesSelect}
            <button
              className="btn pri"
              aria-disabled={!canRun || starting}
              onClick={() => void start()}
            >
              {starting ? "Starting…" : "Run"}
            </button>
          </div>
        )}
      </div>
      <Footer />
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
