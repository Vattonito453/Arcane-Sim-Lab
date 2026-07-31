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
import ApiBaseSetting from "@/components/ApiBaseSetting";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";

interface Health {
  rules: number;
  keywords: number;
  glossary_terms: number;
}

/** Counter that rolls up on load (spec §6). Honours prefers-reduced-motion by
 *  rendering the final value immediately; the wrapper is aria-live="off" so the
 *  roll is never announced. */
function useTally(target: number): number {
  const [v, setV] = useState(0);
  const done = useRef(false);
  useEffect(() => {
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
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return v;
}

function TallyCell({
  badge,
  value,
  label,
}: {
  badge: React.ReactNode;
  value: number;
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

/* Tally badges — spec markup: 34px rounded tile, ringed disc icon. */
const BADGE_SUN = (
  <span className="tally-badge" data-tone="sun">
    <svg width="22" height="22" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="11" fill="#292010" stroke="#F59E0B" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="4" fill="#FDE68A" />
      <path
        d="M12 3v3 M12 18v3 M3 12h3 M18 12h3 M5.6 5.6l2.1 2.1 M16.3 16.3l2.1 2.1 M5.6 18.4l2.1-2.1 M16.3 7.7l2.1-2.1"
        fill="none" stroke="#F59E0B" strokeWidth="1.5" strokeLinecap="round"
      />
    </svg>
  </span>
);
const BADGE_WATER = (
  <span className="tally-badge" data-tone="water">
    <svg width="22" height="22" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="11" fill="#092537" stroke="#00E5FF" strokeWidth="1.5" />
      <path d="M12 4 C12 4 6 11 6 15 A6 6 0 0 0 18 15 C18 11 12 4 12 4 Z" fill="#00E5FF" />
    </svg>
  </span>
);
const BADGE_SKULL = (
  <span className="tally-badge" data-tone="skull">
    <svg width="22" height="22" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="11" fill="#1D1526" stroke="#A855F7" strokeWidth="1.5" />
      <path d="M8 10 a4 4 0 0 1 8 0 c0 3 -1.5 4 -2 6 h-4 c-.5 -2 -2 -3 -2 -6 Z" fill="#C084FC" />
      <circle cx="10" cy="10" r="1" fill="#1D1526" />
      <circle cx="14" cy="10" r="1" fill="#1D1526" />
    </svg>
  </span>
);
const BADGE_COMBO = (
  <span className="tally-badge" data-tone="combo">
    <svg width="22" height="22" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="11" fill="#08201E" stroke="#2DD4BF" strokeWidth="1.5" />
      <path d="M12 5 19 12 12 19 5 12Z" fill="none" stroke="#2DD4BF" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M12 8.6 15.4 12 12 15.4 8.6 12Z" fill="#5EEAD4" />
    </svg>
  </span>
);

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
  const [down, setDown] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let stop = false;
    setDown(false);
    api.decks().then((d) => !stop && setDecks(d)).catch(() => !stop && setDown(true));
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
          <TallyCell badge={BADGE_SUN} value={decks?.length ?? 0} label="decks on this engine" />
          <TallyCell badge={BADGE_WATER} value={view?.totalGames ?? 0} label="games simulated" />
          <TallyCell badge={BADGE_SKULL} value={view?.runs ?? 0} label="finished runs" />
          <TallyCell badge={BADGE_COMBO} value={health?.rules ?? 0} label="rules loaded" />
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
          <Link className="action-btn action-btn--neutral" href="/new">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#C3CEDA" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-4-4" />
            </svg>
            Explore decklists
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
                <Link className="bl" href="/new">
                  All {decks?.length ?? "—"}
                </Link>
              </span>
            </div>
            {!view || view.top.length === 0 ? (
              <p className="note">
                No finished runs yet —{" "}
                <Link className="bl" href="/new">
                  run a gauntlet
                </Link>{" "}
                and the leaderboard builds itself.
              </p>
            ) : (
              <>
                <div className="deck-rows">
                  {view.top.map((d) => (
                    <Link
                      key={d.name}
                      className="deck-row"
                      href={`/results?q=${encodeURIComponent(d.name)}`}
                    >
                      <span className="deck-row__thumb" />
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
                  ))}
                </div>
                <p className="note">
                  Win rates pool every pod size and seat, so compare a deck against its own pod&apos;s
                  baseline in the run report — not against this list.
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

        <p className="splash-engine">
          <ApiBaseSetting onChanged={() => setReloadKey((k) => k + 1)} />
        </p>
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
