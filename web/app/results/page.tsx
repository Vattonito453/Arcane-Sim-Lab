"use client";

/** Run index — /results
 *
 *  This used to be a section at the bottom of the home page, below the deck
 *  picker, which made home do two unrelated jobs and buried the runs. It is now
 *  the "Results" nav item.
 *
 *  Reads GET /results, which is a summary index — a few KB — not the runs
 *  themselves. */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { ResultIndexEntry, SimSummary } from "@/lib/types";
import { deckSlug, fmtDate, pct, runTitle, stripAi, timeAgo } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";

const ENGINE_CMD = "python3 engine/mtg_engine.py serve 8484";
const PAGE = 25;

function topWin(s: SimSummary): [string, number] | null {
  const entries = Object.entries(s.win_rates);
  if (entries.length === 0) return null;
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0];
}

export default function ResultsIndexPage() {
  const [results, setResults] = useState<ResultIndexEntry[] | null>(null);
  const [err, setErr] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    let stop = false;
    api
      .results()
      .then((r) => !stop && setResults(r))
      .catch(() => !stop && setErr(true));
    return () => {
      stop = true;
    };
  }, []);

  const rows = useMemo(() => {
    if (!results) return null;
    return [...results]
      .sort((a, b) => b.modified - a.modified)
      .map((r) => {
        const names = r.summary
          ? Object.keys(r.summary.win_rates).map(stripAi)
          : (r.decks ?? []).map(deckSlug);
        return { r, names, title: runTitle(names), win: r.summary ? topWin(r.summary) : null };
      });
  }, [results]);

  const filtered = useMemo(() => {
    if (!rows) return null;
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (x) =>
        x.title.toLowerCase().includes(needle) ||
        x.names.some((n) => n.toLowerCase().includes(needle)) ||
        x.r.file.toLowerCase().includes(needle),
    );
  }, [rows, q]);

  const visible = filtered ? (showAll ? filtered : filtered.slice(0, PAGE)) : [];
  const totalGames = rows?.reduce((a, x) => a + (x.r.games ?? x.r.summary?.games ?? 0), 0) ?? 0;

  return (
    <>
      <Chrome />
      <div className="page">
        <h1>Results</h1>

        {err ? (
          <p className="lede">
            The engine isn&apos;t answering, so past runs can&apos;t be listed. Start it with{" "}
            <span className="mono">{ENGINE_CMD}</span> and reload.
          </p>
        ) : !rows ? (
          <p className="lede">Loading past runs…</p>
        ) : rows.length === 0 ? (
          <p className="lede">
            No finished runs yet.{" "}
            <Link className="bl" href="/">
              Pick some decks
            </Link>{" "}
            and the results will land here.
          </p>
        ) : (
          <p className="lede">
            <b>{rows.length} finished runs</b> covering{" "}
            <b>{totalGames.toLocaleString("en-US")} games</b>. Open one to see win rates
            against the even-seats baseline, or jump straight into a replay.
          </p>
        )}

        {rows && rows.length > 0 && (
          <section>
            <div className="tblwrap">
              <div className="toolrow">
                <div className="inp">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="11" cy="11" r="7" />
                    <path d="m21 21-4.3-4.3" />
                  </svg>
                  <input
                    value={q}
                    placeholder="Filter by deck…"
                    aria-label="Filter runs"
                    onChange={(e) => setQ(e.target.value)}
                  />
                </div>
                <span className="upd">
                  {filtered?.length ?? 0} of {rows.length} runs
                </span>
              </div>
              <table className="games">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th className="r">Games</th>
                    <th>Winner</th>
                    <th className="r">When</th>
                    <th className="r">Replay</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map(({ r, title, win }) => {
                    const enc = encodeURIComponent(r.file);
                    return (
                      <tr key={r.file}>
                        <td>
                          {/* The matchup, not the result filename — the filename is
                              only the address, so it lives in the row title. */}
                          <Link className="q" href={`/results/${enc}`} title={r.file}>
                            {title}
                          </Link>
                        </td>
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
                        <td className="r" title={fmtDate(r.modified)}>
                          {timeAgo(r.modified)}
                        </td>
                        <td className="r">
                          <Link className="bl" href={`/results/${enc}/replay/1`}>
                            Watch
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {(filtered?.length ?? 0) > PAGE && (
                <div className="pager">
                  <span>
                    Showing {visible.length} of {filtered?.length} runs
                  </span>
                  <a
                    className="bl"
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setShowAll((v) => !v);
                    }}
                  >
                    {showAll ? "Show fewer" : "Show all"}
                  </a>
                </div>
              )}
            </div>
          </section>
        )}
      </div>
      <Footer />
    </>
  );
}
