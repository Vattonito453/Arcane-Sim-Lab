"use client";

/** Home — the splash hub (Design System/Sim Lab Splash.dc.html).
 *
 *  Masthead → rolling tally banner → "What would you like to do today?" +
 *  action hub → one glass data panel (top decklists · most recent sims).
 *
 *  Every figure on this page is computed from the live engine — the mockup's
 *  counters (52,365 decks tested…) are placeholder art, not targets. Where the
 *  mockup shows things this product doesn't have (accounts, calculators, an
 *  advertisement slot), the slot is omitted rather than faked. */

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { DeckEntry, ResultIndexEntry } from "@/lib/types";
import { pct, runTitle, stripAi, timeAgo } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";
import { Mascot } from "@/components/Mascot";
import { PIP_SRC } from "@/components/ManaPips";
import { factsKey } from "@/components/DeckGallery";
import { loadCards, type CardMap } from "@/lib/cards";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";

interface Health {
  rules: number;
  keywords: number;
  glossary_terms: number;
}

/** Counter that rolls up on load (spec §6). Honours prefers-reduced-motion by
 *  rendering the final value immediately; the wrapper is aria-live="off" so the
 *  roll is never announced. */
function useTally(target: number | null): number {
  const [v, setV] = useState(0);
  const done = useRef(false);
  useEffect(() => {
    // Nothing to roll to yet (fetch still in flight) — don't animate toward
    // the 0 placeholder, or the real value arriving a moment later would
    // restart the roll from scratch instead of playing once on load.
    if (target == null) return;
    if (done.current) {
      setV(target);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      done.current = true;
      setV(target);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const dur = 1400; // --dur-tally
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setV(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(step);
      else done.current = true;
    };
    raf = requestAnimationFrame(step);
    // A backgrounded tab throttles or fully suspends requestAnimationFrame,
    // which can strand the counter mid-roll with no way to recover. This
    // timer guarantees the true value lands even if no frame ever fires.
    const fallback = setTimeout(() => {
      done.current = true;
      setV(target);
    }, dur + 200);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(fallback);
    };
  }, [target]);
  return v;
}

function TallyCell({
  badge,
  value,
  label,
}: {
  badge: React.ReactNode;
  value: number | null;
  label: string;
}) {
  const v = useTally(value);
  return (
    <div className="tally-cell">
      {badge}
      <span className="tally-text">
        <b className="mono">{v.toLocaleString("en-US")}</b> {label}
      </span>
    </div>
  );
}

/* Tally badges: the mana medallion alone in a bare 34px slot, no tinted tile
 * behind it (see .tally-badge). The medallions are ornament here, not colour
 * identity, so they take alt="" and each cell's text carries the meaning. They
 * were previously hand-drawn copies of the old pip SVGs, which then went stale
 * when the pips became artwork; drawing them from PIP_SRC keeps one source.
 * "Rules loaded" is not a colour, so it takes the colourless medallion. */
function TallyPip({ src }: { src: string }) {
  return (
    <span className="tally-badge">
      <img src={src} width={30} height={30} alt="" draggable={false} />
    </span>
  );
}
const BADGE_SUN = <TallyPip src={PIP_SRC.W} />;
const BADGE_WATER = <TallyPip src={PIP_SRC.U} />;
const BADGE_FIRE = <TallyPip src={PIP_SRC.R} />;
const BADGE_COMBO = <TallyPip src={PIP_SRC.C} />;

interface DeckAgg {
  name: string;
  runs: number;
  wins: number;
  games: number;
  rate: number;
}

export default function Home() {
  const [decks, setDecks] = useState<DeckEntry[] | null>(null);
  const [results, setResults] = useState<ResultIndexEntry[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [facts, setFacts] = useState<CardMap>({});
  const [down, setDown] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let stop = false;
    setDown(false);
    api
      .decks()
      .then(async (d) => {
        if (stop) return;
        setDecks(d);
        // Same one batched, engine-cached call the galleries make — it fills the
        // leaderboard thumbnails, which used to be a hardcoded stripe pattern
        // standing in for art we already had.
        const commanders = d.map((x) => x.commander).filter((c): c is string => !!c);
        const map = await loadCards(commanders);
        if (!stop) setFacts({ ...map });
      })
      .catch(() => !stop && setDown(true));
    api.results().then((r) => !stop && setResults(r)).catch(() => {});
    api.health().then((h) => !stop && setHealth(h)).catch(() => {});
    return () => {
      stop = true;
    };
  }, [reloadKey]);

  const view = useMemo(() => {
    if (!results) return null;
    const sorted = [...results].sort((a, b) => b.modified - a.modified);
    const finished = sorted.filter((r) => !r.error);
    const totalGames = finished.reduce((a, r) => a + (r.games ?? r.summary?.games ?? 0), 0);

    // Per-deck aggregate across every finished run it appeared in.
    const agg = new Map<string, DeckAgg>();
    for (const r of finished) {
      if (!r.summary) continue;
      const games = r.summary.games;
      const seats = new Set(Object.keys(r.summary.win_rates).map(stripAi));
      for (const name of seats) {
        const a = agg.get(name) ?? { name, runs: 0, wins: 0, games: 0, rate: 0 };
        a.runs += 1;
        a.games += games;
        agg.set(name, a);
      }
      for (const [key, w] of Object.entries(r.summary.wins)) {
        const a = agg.get(stripAi(key));
        if (a) a.wins += w;
      }
    }
    const top = [...agg.values()]
      .map((a) => ({ ...a, rate: a.games > 0 ? a.wins / a.games : 0 }))
      .sort((a, b) => b.runs - a.runs || b.rate - a.rate)
      .slice(0, 5);

    const recent = finished
      .filter((r) => r.summary)
      .slice(0, 4)
      .map((r) => {
        const names = Object.keys(r.summary!.win_rates).map(stripAi);
        const best = Object.entries(r.summary!.win_rates).sort((a, b) => b[1] - a[1])[0];
        return {
          file: r.file,
          title: runTitle(names),
          winner: best ? stripAi(best[0]) : null,
          rate: best ? best[1] : 0,
          games: r.games ?? r.summary!.games,
          when: timeAgo(r.modified),
        };
      });

    return { runs: finished.length, totalGames, top, recent };
  }, [results]);

  return (
    <>
      <Chrome noBrand />
      {/* Masthead (§6): mascot directly above the wordmark, one locked brand
          unit on the quiet upper sky of the backdrop. */}
      <div className="masthead">
        <Mascot />
        <h1 className="wordmark">Arcane Sim Lab</h1>
        {down && (
          <p className="prompt">
            The engine at the configured address isn&apos;t answering. Start it with{" "}
            <span className="mono">{ENGINE_CMD}</span>{" "}
            <a
              className="bl"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setReloadKey((k) => k + 1);
              }}
            >
              and retry
            </a>
            .
          </p>
        )}
      </div>

      <div className="splash">
        {/* Rolling tally banner — real figures from this engine, not the
            mockup's placeholders. aria-live off: the roll is never announced. */}
        <div className="tally" aria-live="off">
          <TallyCell badge={BADGE_SUN} value={decks?.length ?? null} label="decks on this engine" />
          <TallyCell badge={BADGE_WATER} value={view?.totalGames ?? null} label="games simulated" />
          <TallyCell badge={BADGE_FIRE} value={view?.runs ?? null} label="finished runs" />
          <TallyCell badge={BADGE_COMBO} value={health?.rules ?? null} label="rules loaded" />
        </div>

        <p className="splash-prompt">What would you like to do today?</p>

        {/* Action hub (§6): four equal footprints; border and glow do the
            ranking. Identity pips never appear in these buttons. */}
        <div className="hub">
          <Link className="action-btn action-btn--primary" href="/new">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="#00E5FF" aria-hidden="true">
              <path d="M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12Z" />
            </svg>
            Run new simulation
          </Link>
          <Link className="action-btn action-btn--violet" href="/results">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#C89BFA" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M5 20V9M12 20V4M19 20v-7" />
            </svg>
            Sim history &amp; analytics
          </Link>
          <Link className="action-btn action-btn--blue" href="/import">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#7DD3FC" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v11m-4.5-4.5L12 14l4.5-4.5M4 19h16" />
            </svg>
            Import deck
          </Link>
          {/* Was /new — the same route as "Run new simulation", so two of the
              four buttons went to one place. Browsing has its own page now. */}
          <Link className="action-btn action-btn--neutral" href="/decks">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#C3CEDA" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-4-4" />
            </svg>
            Explore decks
          </Link>
        </div>
        {/* The primary carries its cost estimate (§6): pod size, not game
            count, drives the wait. */}
        <p className="hub-est">two decks ≈ 5 s a game · four decks ≈ 8 min for 16</p>

        {/* One glass sheet holds both columns — panels never nest. */}
        <div className="glass-panel datapanel">
          <div>
            <div className="sh">
              <h2>Top decklists</h2>
              <span className="meta">most run</span>
              <span className="right">
                <Link className="bl" href="/decks">
                  All {decks?.length ?? "–"}
                </Link>
              </span>
            </div>
            {!view || view.top.length === 0 ? (
              <p className="note">
                No finished runs yet.{" "}
                <Link className="bl" href="/new">
                  Run a gauntlet
                </Link>{" "}
                and the leaderboard builds itself.
              </p>
            ) : (
              <>
                <div className="deck-rows">
                  {view.top.map((d) => {
                    // The heading says decklists, so the row opens the deck. It
                    // used to open a filtered run list, which is a different
                    // thing wearing the same label.
                    const entry = decks?.find((x) => x.name === d.name);
                    const art = entry?.commander
                      ? (facts[factsKey(entry.commander)]?.art_crop ?? null)
                      : null;
                    return (
                      <Link
                        key={d.name}
                        className="deck-row"
                        href={
                          entry
                            ? `/decks/${encodeURIComponent(entry.file)}`
                            : `/results?q=${encodeURIComponent(d.name)}`
                        }
                      >
                        <span className="deck-row__thumb">
                          {art && (
                            // eslint-disable-next-line @next/next/no-img-element -- Scryfall hotlink
                            <img src={art} alt="" loading="lazy" />
                          )}
                        </span>
                        <span className="deck-row__body">
                          <span
                            className="deck-row__fill"
                            style={{ width: `${Math.round(d.rate * 100)}%` }}
                          />
                          <span className="deck-row__name">{d.name}</span>
                          <span className="deck-row__meta">
                            {d.runs} {d.runs === 1 ? "run" : "runs"}
                          </span>
                        </span>
                        <span className="deck-row__pct mono">{pct(d.rate)}</span>
                      </Link>
                    );
                  })}
                </div>
                <p className="note">
                  Pooled across every pod and seat, so read a deck against its own pod&apos;s
                  baseline in the run report, not against this list.
                </p>
              </>
            )}
          </div>

          <div>
            <div className="sh">
              <h2>Most recent sims</h2>
              <span className="meta">{view ? `${view.runs} finished` : "loading…"}</span>
              <span className="right">
                <Link className="bl" href="/results">
                  All results
                </Link>
              </span>
            </div>
            {!view || view.recent.length === 0 ? (
              <p className="note">Finished runs land here.</p>
            ) : (
              view.recent.map((r) => (
                <Link
                  key={r.file}
                  className="simrow"
                  href={`/results/${encodeURIComponent(r.file)}`}
                >
                  <span className="simrow__title">{r.title}</span>
                  <span className="simrow__meta">
                    <b>
                      {r.winner ?? "Draw"} {pct(r.rate)}
                    </b>{" "}
                    · {r.games} {r.games === 1 ? "game" : "games"} · {r.when}
                  </span>
                </Link>
              ))
            )}
          </div>
        </div>

      </div>

      <Footer />
    </>
  );
}
