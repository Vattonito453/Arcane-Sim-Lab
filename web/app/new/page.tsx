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
 *  real setting and lives once, in the nav sheet (dev builds only).
 *
 *  ?deck= preselects (import links here).
 *
 *  Game counts are whole seat rotations only. Every run rotates seats, and the
 *  engine rounds a request up until each deck sits in every seat equally, so
 *  "16 games" for three decks used to play 18 while the button said 16. The
 *  choice here is how often each deck goes first; the count on the button is
 *  the count that will be played. The duration beside it is the engine's own
 *  (GET /estimate), the same range the run page shows once it starts. */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, type SimEstimate } from "@/lib/api";
import type { DeckEntry } from "@/lib/types";
import { fmtRange, plural, timesWord } from "@/lib/format";
import { Chrome, EngineDown, Footer } from "@/components/Chrome";
import { DeckGallery, factsKey } from "@/components/DeckGallery";
import { loadCards, type CardMap } from "@/lib/cards";

/** How many times each deck takes the first seat. Games = this x pod size. */
const STARTS = [1, 2, 4, 8];

function NewRunInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselect = searchParams.get("deck");

  const [decks, setDecks] = useState<DeckEntry[] | null>(null);
  const [facts, setFacts] = useState<CardMap>({});
  const [down, setDown] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [selected, setSelected] = useState<string[]>([]);
  // Four starts each: 16 games for a 4-deck pod, the old default.
  const [starts, setStarts] = useState(4);
  const [est, setEst] = useState<SimEstimate | null>(null);
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

  const podSize = selected.length;
  const canRun = podSize >= 2 && podSize <= 4;
  const requested = podSize * starts;
  const selectedDecks = selected
    .map((f) => decks?.find((d) => d.file === f))
    .filter((d): d is DeckEntry => !!d);

  // The engine's figure for exactly this pod size and count. Nothing is shown
  // while it loads or if it fails: a missing estimate is better than a
  // made-up one, which is what the old client-side table was.
  useEffect(() => {
    if (!canRun) return;
    let stop = false;
    api
      .estimate(podSize, requested)
      .then((e) => !stop && setEst(e))
      .catch(() => {});
    return () => {
      stop = true;
    };
  }, [canRun, podSize, requested]);
  const estimate =
    est && est.decks === podSize && est.games_requested === requested ? est : null;
  // Every production run rotates seats. Only an engine that has said
  // otherwise (MTG_SIM_ROTATE=0, a debugging switch) gets seat-order copy.
  const rotating = est ? est.rotations === est.decks : true;
  const played = estimate?.games_to_play ?? requested;

  const gamesLabel = (k: number, short: boolean): string => {
    if (podSize < 2) return short ? `${timesWord(k)} each` : `Each deck starts ${timesWord(k)}`;
    const count = plural(podSize * k, "game");
    return short || !rotating ? count : `${count} (each deck starts ${timesWord(k)})`;
  };

  const start = async () => {
    if (!canRun || starting) return;
    setStarting(true);
    setStartErr(null);
    try {
      const r = await api.simulate(selected, requested);
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

  const gamesSelect = (short: boolean) => (
    <select
      className="sel"
      value={starts}
      aria-label="Games to simulate"
      onChange={(e) => setStarts(Number(e.target.value))}
    >
      {STARTS.map((k) => (
        <option key={k} value={k}>
          {gamesLabel(k, short)}
        </option>
      ))}
    </select>
  );

  const closeTabNote = "You can close this tab; it lands in Results when it's done.";

  return (
    <>
      <Chrome />
      <div className="page">
        <h1>Simulate</h1>

        {down ? (
          <EngineDown onRetry={reload} />
        ) : !decks ? (
          <p className="lede">Loading decks…</p>
        ) : (
          <p className="lede">
            Tap two to four decks to seat them, then run the gauntlet.
          </p>
        )}

        {down ? null : !decks ? (
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
                {/* Was "Seat order is the order you pick", which every rotated
                    run contradicts. */}
                {selectedDecks.length === 0 && (
                  <p className="note">
                    {rotating
                      ? "Every deck takes every seat, so order doesn't matter."
                      : "Decks sit in the order you pick."}
                  </p>
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
                    {gamesSelect(false)}
                  </div>
                  <div className="ctarow">
                    {/* The primary stays live (DESIGN_SYSTEM.md §6): when the run
                        can't start, the blocker is stated beside it instead. It
                        carries the PLAYED count, which the engine confirms. */}
                    <button
                      className="btn pri"
                      aria-disabled={!canRun || starting}
                      aria-describedby={canRun ? "run-estimate" : "run-blocker"}
                      onClick={() => void start()}
                    >
                      {starting
                        ? "Starting sim…"
                        : canRun
                          ? `Run ${plural(played, "game")}`
                          : "Run sim"}
                    </button>
                  </div>
                  {!canRun && (
                    <p className="ctanote" id="run-blocker">
                      Pick at least 2 decks; you have {podSize}.
                    </p>
                  )}
                  {canRun && (
                    // Shown before you commit: this is the only number anyone
                    // sees before an hour-long job, so it is the engine's.
                    <p className="ctanote" id="run-estimate">
                      {estimate && (
                        <>
                          Usually{" "}
                          <span className="mono">
                            {fmtRange(estimate.typical_seconds[0], estimate.typical_seconds[1])}
                          </span>
                          .{" "}
                        </>
                      )}
                      {closeTabNote}
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
                  <b>{podSize}</b> seated
                  {estimate && (
                    <>
                      {" · usually "}
                      <span className="mono">
                        {fmtRange(estimate.typical_seconds[0], estimate.typical_seconds[1], true)}
                      </span>
                    </>
                  )}
                  <small>{selectedDecks.map((d) => d.name).join(" · ")}</small>
                </>
              ) : (
                <>
                  <b>{podSize}</b> of 2–4 seated
                  <small>Pick at least 2 to run</small>
                </>
              )}
            </span>
            {/* Short labels here ("16 games"): the select sits right beside the
                button, so the played count is on screen without repeating it. */}
            {gamesSelect(true)}
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
