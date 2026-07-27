"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { DeckEntry, ResultIndexEntry, SimSummary } from "@/lib/types";
import { deckSlug, pct, stripAi, timeAgo } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";
import ApiBaseSetting from "@/components/ApiBaseSetting";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";
const RUNS_SHOWN = 12;

interface Health {
  rules: number;
  keywords: number;
  glossary_terms: number;
}

function topWin(s: SimSummary): [string, number] | null {
  const entries = Object.entries(s.win_rates);
  if (entries.length === 0) return null;
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0];
}

function HomeInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselect = searchParams.get("deck");

  const [decks, setDecks] = useState<DeckEntry[] | null>(null);
  const [results, setResults] = useState<ResultIndexEntry[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  const [healthErr, setHealthErr] = useState(false);
  const [resultsErr, setResultsErr] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [selected, setSelected] = useState<string[]>([]);
  const [games, setGames] = useState(16);
  const [starting, setStarting] = useState(false);
  const [startErr, setStartErr] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const appliedPreselect = useRef(false);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let stop = false;
    setDown(false);
    setHealthErr(false);
    setResultsErr(false);
    api
      .health()
      .then((h) => {
        if (!stop) setHealth(h);
      })
      .catch(() => {
        if (!stop) {
          setHealth(null);
          setHealthErr(true);
        }
      });
    api
      .decks()
      .then((d) => {
        if (!stop) setDecks(d);
      })
      .catch(() => {
        if (!stop) {
          setDecks(null);
          setDown(true);
        }
      });
    api
      .results()
      .then((r) => {
        if (!stop) setResults(r);
      })
      .catch(() => {
        if (!stop) {
          setResults(null);
          setResultsErr(true);
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

  const toggle = (file: string) => {
    setStartErr(null);
    setSelected((prev) => {
      if (prev.includes(file)) return prev.filter((f) => f !== file);
      if (prev.length >= 4) return prev;
      return [...prev, file];
    });
  };

  const canRun = selected.length >= 2 && selected.length <= 4;

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

  const sorted = useMemo(
    () => (results ? [...results].sort((a, b) => b.modified - a.modified) : null),
    [results]
  );
  const visible = sorted ? (showAll ? sorted : sorted.slice(0, RUNS_SHOWN)) : [];

  const downNote = (
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
  );

  return (
    <>
      <Chrome />
      <div className="page">
        <h1>Sim Lab</h1>

        {down ? (
          <p className="lede">
            The engine at the configured address isn&apos;t answering. Start it with{" "}
            <span className="mono">{ENGINE_CMD}</span> and retry — nothing here is lost.
          </p>
        ) : !decks ? (
          <p className="lede">Loading decks and past runs…</p>
        ) : (
          <p className="lede">
            <b>{decks.length} decks</b>
            {sorted ? (
              <>
                {" "}
                and <b>{sorted.length} finished runs</b>
              </>
            ) : null}{" "}
            on this engine. Pick two to four decks and run a gauntlet, or import a new list.
          </p>
        )}

        <section>
          <div className="sh">
            <h2>New run</h2>
            <span className="meta">pick two to four decks</span>
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

          {down ? (
            downNote
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
            <>
              <div className="tblwrap">
                <div className="toolrow">
                  {selected.length === 0
                    ? "Select decks by clicking rows"
                    : `${selected.length} of 2–4 selected`}
                  <span className="upd">{decks.length} decks</span>
                </div>
                <table className="games">
                  <tbody>
                    {decks.map((d) => {
                      const on = selected.includes(d.file);
                      return (
                        <tr key={d.file} className="click" onClick={() => toggle(d.file)}>
                          <td>
                            <input
                              type="checkbox"
                              checked={on}
                              aria-label={`Select ${d.name}`}
                              onClick={(e) => e.stopPropagation()}
                              onChange={() => toggle(d.file)}
                            />
                          </td>
                          <td>
                            <div className="by">{d.name}</div>
                          </td>
                          <td className="mono">{d.file}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="ctarow">
                <select
                  className="sel"
                  value={games}
                  aria-label="Games to simulate"
                  onChange={(e) => setGames(Number(e.target.value))}
                >
                  <option value={8}>8 games</option>
                  <option value={16}>16 games</option>
                  <option value={32}>32 games</option>
                </select>
                <button className="btn pri" disabled={!canRun || starting} onClick={() => void start()}>
                  {starting ? "Starting run…" : `Run ${games}-game simulation`}
                </button>
                {selected.length === 1 && (
                  <span className="ctanote">select at least one more deck</span>
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
            </>
          )}
        </section>

        <section>
          <div className="sh">
            <h2>Past runs</h2>
            {sorted && <span className="meta">{sorted.length} on disk</span>}
          </div>

          {resultsErr ? (
            downNote
          ) : !sorted ? (
            <p className="note">Loading past runs…</p>
          ) : sorted.length === 0 ? (
            <p className="note">No finished runs yet — start one above and it will land here.</p>
          ) : (
            <div className="tblwrap">
              <table className="games">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Decks</th>
                    <th className="r">Games</th>
                    <th>Winner</th>
                    <th className="r">When</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => {
                    const names = r.summary
                      ? Object.keys(r.summary.win_rates).map(stripAi)
                      : (r.decks ?? []).map(deckSlug);
                    const win = r.summary ? topWin(r.summary) : null;
                    return (
                      <tr key={r.file}>
                        <td className="id">
                          <Link className="q" href={`/results/${encodeURIComponent(r.file)}`}>
                            {r.file}
                          </Link>
                        </td>
                        <td>{names.join(" · ")}</td>
                        <td className="r mono">{r.games ?? r.summary?.games ?? "—"}</td>
                        <td>
                          {win ? (
                            <>
                              <span className="st win">
                                <i />
                                {stripAi(win[0])}
                              </span>{" "}
                              <span className="mono">{pct(win[1])}</span>
                            </>
                          ) : (
                            <span className="st loss">
                              <i />
                              no summary
                            </span>
                          )}
                        </td>
                        <td className="r">{timeAgo(r.modified)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {sorted.length > RUNS_SHOWN && (
                <div className="pager">
                  <span>
                    Showing {visible.length} of {sorted.length} runs
                  </span>
                  <div className="pg">
                    <button onClick={() => setShowAll((s) => !s)}>
                      {showAll ? "Show fewer" : "Show all"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
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
      <HomeInner />
    </Suspense>
  );
}
