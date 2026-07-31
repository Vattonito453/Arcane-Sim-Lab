"use client";

/** Run results report — /results/[file]
 *  Reads the run *summary* from the engine (GET /results/{file}/summary) and
 *  reports it: prose lede, four headline figures, win-rate rails against the
 *  even-seats baseline, and a games table that links into the replay theater.
 *
 *  The summary carries no event logs — a run that is ~2.4 MB whole arrives here
 *  as a few KB. Anything that needs the event-by-event record (the "decided by"
 *  reason, the folded board) lives in the replay, which fetches one game. */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Chrome, Footer } from "@/components/Chrome";
import { api, RateLimited } from "@/lib/api";
import type { AnalysisReport, RunGameSummary, RunSummary } from "@/lib/types";
import { deckSlug, pct, plural, runTitle, stripAi } from "@/lib/format";

function fmtClock(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : Math.round((s[mid - 1] + s[mid]) / 2);
}

/** Winner key out of a result raw, for the rare run whose result.winner is null
 *  but whose raw still names a winner ("… Ai(2)-Drana Vampires has won!"). */
const RE_WON_RAW = /([^.]+?) has won/;

/** One table row, built entirely from the summary payload. */
interface GameRow {
  n: number;
  winnerName: string | null;
  draw: boolean;
  endedTurn: number;
  durationMs: number;
  decidedBy: string;
}

function toRow(g: RunGameSummary): GameRow {
  const key = g.result.winner ?? g.result.raw.match(RE_WON_RAW)?.[1]?.trim() ?? null;
  const winnerName = key ? stripAi(key) : null;
  const endedTurn = g.ended_turn ?? g.turns;
  // Without the event log there is no honest way to name the killing swing, so
  // this column states only what the result line proves: who won, and when.
  const decidedBy = g.result.draw
    ? "Draw"
    : winnerName
      ? endedTurn
        ? `${winnerName} won on turn ${endedTurn}`
        : `${winnerName} won`
      : "—";
  return {
    n: g.n,
    winnerName,
    draw: g.result.draw,
    endedTurn,
    durationMs: g.result.duration_ms,
    decidedBy,
  };
}

export default function ResultsPage() {
  const params = useParams<{ file: string }>();
  const router = useRouter();
  const file = decodeURIComponent(String(params?.file ?? ""));

  const [data, setData] = useState<RunSummary | null>(null);
  const [an, setAn] = useState<AnalysisReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [wait, setWait] = useState<number | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let live = true;
    api
      .runSummary(file)
      .then((r) => live && setData(r))
      .catch((e: unknown) => {
        if (!live) return;
        if (e instanceof RateLimited) {
          setWait(e.retryAfter);
          setErr(e.message);
        } else {
          setErr(e instanceof Error ? e.message : String(e));
        }
      });
    // Wincon analysis loads separately and the page works without it — the
    // first request for an old run computes it server-side, which can take a
    // few seconds, and a failure just means no Win conditions section.
    api.analysis(file).then((r) => live && setAn(r)).catch(() => {});
    return () => {
      live = false;
    };
  }, [file]);

  const view = useMemo(() => {
    if (!data) return null;
    const games = data.games.length;

    // The pod roster comes from the games, not from summary.win_rates, for two
    // reasons. A winless deck is missing from the summary of any run adapted
    // before that was fixed, and reading the roster off the summary sizes a
    // 4-deck pod as a 1-deck pod — which sets the even-seats baseline to 100%.
    // Rotated runs also key the summary by bare deck name while games[].players
    // keep the Ai(n)- seat prefix; folding both through stripAi() puts the two
    // in one namespace, so every row below is already a display label.
    const wins = new Map<string, number>();
    for (const g of data.games) for (const p of g.players) wins.set(stripAi(p), 0);
    for (const [key, w] of Object.entries(data.summary.wins)) {
      const label = stripAi(key);
      wins.set(label, (wins.get(label) ?? 0) + w);
    }
    const baseline = wins.size > 0 ? 1 / wins.size : 0.25;
    const rows = [...wins.entries()]
      // Recomputed rather than read from win_rates: that map is keyed the same
      // way and would reintroduce the raw-vs-stripped mismatch.
      .map(([name, w]) => ({ name, wins: w, rate: games > 0 ? w / games : 0 }))
      .sort((a, b) => b.rate - a.rate || a.name.localeCompare(b.name));
    const maxWins = rows.length ? rows[0].wins : 0;
    const tops = rows.filter((r) => r.wins === maxWins);
    const topNames = new Set(tops.map((t) => t.name));
    const gameRows: GameRow[] = data.games.map(toRow);
    const medTurns = median(gameRows.map((g) => g.endedTurn));
    const rotated = data.meta?.source === "rotated";

    // Chrome context: first deck of the run. The commander-art guess needs cast
    // events from the logs, which the summary does not carry — so the breadcrumb
    // shows the deck name alone here, and the replay keeps the art.
    const firstDeckFile = data.meta.decks?.[0] ?? "";
    const ctx = firstDeckFile ? deckSlug(firstDeckFile) : file.replace(/\.json$/, "");

    // First game the leading deck actually won — target for the primary action.
    let watchGame = 1;
    for (const g of gameRows) {
      if (g.winnerName && topNames.has(g.winnerName)) {
        watchGame = g.n;
        break;
      }
    }
    return { games, baseline, rows, tops, topNames, gameRows, medTurns, rotated, ctx, watchGame };
  }, [data, file]);

  // The matchup, not the filename: "sim_20260724_094940_rotated.json" tells a
  // reader nothing. The filename stays in the sub-line and the footer for anyone
  // who needs to find it on disk.
  const title = view ? runTitle(view.rows.map((r) => r.name)) : file.replace(/\.json$/, "");
  const enc = encodeURIComponent(file);

  if (err) {
    return (
      <>
        <Chrome tabs={[{ label: "Overview", href: "#", on: true }]} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">{wait != null ? "Rate limited" : "Could not load this result"}</div>
            </div>
          </div>
          {wait != null ? (
            <p className="note">
              {err} — the engine is throttling reads. Try again in about{" "}
              <span className="mono">{wait}</span> s.
            </p>
          ) : (
            <p className="note">{err} — check that the engine API is running, then reload.</p>
          )}
        </div>
        <Footer right={file} />
      </>
    );
  }
  if (!data || !view) {
    return (
      <>
        <Chrome tabs={[{ label: "Overview", href: "#", on: true }]} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">Loading result…</div>
            </div>
          </div>
        </div>
        <Footer right={file} />
      </>
    );
  }

  const { rows, tops, topNames, gameRows, games, baseline, medTurns, rotated } = view;
  const top = rows[0];
  const second = rows.find((r) => !topNames.has(r.name));
  const draws = data.summary.draws;
  const gameWord = rotated ? "seat-rotated games" : "games";

  const filtered = gameRows.filter((g) => {
    if (!q.trim()) return true;
    const needle = q.trim().toLowerCase();
    return (
      (g.winnerName ?? "draw").toLowerCase().includes(needle) ||
      g.decidedBy.toLowerCase().includes(needle) ||
      `t${g.endedTurn}`.includes(needle)
    );
  });

  const tieText =
    tops.length > 1
      ? ` — tied with ${tops.slice(1).map((t) => t.name).join(" and ")}`
      : second
        ? `, ${top.wins - second.wins} ${top.wins - second.wins === 1 ? "win" : "wins"} clear of ${second.name} (${pct(second.rate)})`
        : "";

  return (
    <>
      <Chrome context={view.ctx} tabs={[{ label: "Overview", href: "#", on: true }]} />
      <div className="page">
        <div className="head">
          <div>
            <h1>{title}</h1>
            <div className="sub">
              {rows.map((r) => r.name).join(" · ")}
              <span className="sep">·</span>
              <span className="mono">{file}</span>
              <span className="sep">·</span>
              <span className="mono">{games}</span> {games === 1 ? "game" : "games"}
              <span className="sep">·</span>
              {String(data.meta?.format ?? "Commander")}
            </div>
          </div>
          <div className="btns">
            <Link className="btn pri" href={`/results/${enc}/replay/${view.watchGame}`}>
              Watch a winning game
            </Link>
          </div>
        </div>

        <p className="lede">
          <b>{top.name}</b> won <b>{top.wins} of {games}</b> {gameWord} ({pct(top.rate)})
          {tieText}.{" "}
          {draws > 0 ? (
            <>
              {draws} {draws === 1 ? "game" : "games"} ended drawn; the median game ran{" "}
              <b>{medTurns} turns</b>.
            </>
          ) : (
            <>No draws; the median game ran <b>{medTurns} turns</b>.</>
          )}
        </p>

        <div className="figs">
          <div className="fig">
            <div className="n">{games}</div>
            <div className="l">games in this run</div>
          </div>
          <div className="fig">
            <div className="n">{medTurns}</div>
            <div className="l">median turns per game</div>
          </div>
          <div className="fig">
            <div className="n">
              {(top.rate * 100).toFixed(0)}
              <small>%</small>
            </div>
            <div className="l">top win rate — {top.name}</div>
          </div>
          <div className="fig">
            <div className="n">{draws}</div>
            <div className="l">{draws === 1 ? "draw" : "draws"}</div>
          </div>
        </div>

        <section>
          <div className="sh">
            <h2>Win rates</h2>
            <span className="meta">
              {plural(games, "game")}, {plural(rows.length, "deck")}
            </span>
          </div>
          <table className="podt">
            <tbody>
              {rows.map((r) => (
                <tr key={r.name}>
                  <td className="nm">{r.name}</td>
                  <td>
                    <div className="rail">
                      <div className="fill" style={{ width: `${Math.max(r.rate * 100, r.wins > 0 ? 1 : 0)}%` }} />
                      <div className="base" style={{ left: `${baseline * 100}%` }} />
                    </div>
                  </td>
                  <td className="pct">{pct(r.rate)}</td>
                  <td className="res">
                    <span className={`st ${r.wins === 0 ? "bad" : r.rate >= baseline ? "win" : "loss"}`}>
                      <i />
                      {r.wins} of {games}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">
            The thin marker on each bar sits at {pct(baseline, 1)} — the even-seats baseline for a{" "}
            {rows.length}-player pod. A deck to the right of it is beating an equal share of its games.
          </p>
        </section>

        {an && Object.values(an.decks).some((d) => d.combos.length > 0 || d.combo_status === "unknown") && (
          <section>
            <div className="sh">
              <h2>Win conditions</h2>
              <span className="meta">
                known combos via Commander Spellbook · assembly inferred from the event log
              </span>
            </div>
            <div className="tblwrap">
              <table className="games">
                <thead>
                  <tr>
                    <th>Deck</th>
                    <th>Combo</th>
                    <th className="r">Assembled</th>
                    <th className="r">Converted</th>
                    <th>Reading</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(an.decks).flatMap(([name, d]) => {
                    if (d.combo_status === "unknown") {
                      return [
                        <tr key={`${name}-unknown`}>
                          <td>{name}</td>
                          <td colSpan={4} className="ctanote">
                            combos unknown — Spellbook was unreachable when this was analysed
                          </td>
                        </tr>,
                      ];
                    }
                    if (d.combos.length === 0) {
                      return [
                        <tr key={`${name}-none`}>
                          <td>{name}</td>
                          <td colSpan={4} className="ctanote">
                            no known combos in the 99
                            {d.almost_included > 0 && (
                              <> · <span className="mono">{d.almost_included}</span> one card away</>
                            )}
                          </td>
                        </tr>,
                      ];
                    }
                    return d.combos.map((c) => {
                      // The reading is the product: does this deck's win rate
                      // mean anything, or is the AI the bottleneck?
                      const fired = c.converted_games > 0;
                      const stuck = c.assembled_games > 0 && !fired;
                      return (
                        <tr key={`${name}-${c.id}`}>
                          <td>{name}</td>
                          <td title={c.produces.join(", ")}>{c.cards.join(" + ")}</td>
                          <td className="r mono">
                            {c.assembled_games} of {c.games_played}
                            {c.median_assembled_turn != null && <> (T{c.median_assembled_turn})</>}
                          </td>
                          <td className="r mono">{c.converted_games}</td>
                          <td>
                            {fired ? (
                              <span className="st win">
                                <i />
                                AI can fire this — results meaningful
                              </span>
                            ) : stuck ? (
                              <span className="st warn">
                                <i />
                                assembled, never fired — win rate is a floor
                              </span>
                            ) : (
                              <span className="st loss">
                                <i />
                                never assembled in this run
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    });
                  })}
                </tbody>
              </table>
              <p className="note">
                Assembled counts games where every piece was on the battlefield at once, from board
                reconstruction — an inference, not a read. Converted means that seat then won.
                {Object.values(an.decks).some((d) => d.combos.some((c) => c.idle_online_turns > 0)) && (
                  <>
                    {" "}Combos here sat fully online{" "}
                    <span className="mono">
                      {Object.values(an.decks).reduce(
                        (a, d) => a + d.combos.reduce((x, c) => x + c.idle_online_turns, 0), 0)}
                    </span>{" "}
                    turns without winning — Forge&apos;s AI does not pilot loops, so treat those decks&apos;
                    numbers as a floor, not a verdict.
                  </>
                )}
              </p>
            </div>
          </section>
        )}

        <section>
          <div className="sh">
            <h2>Games</h2>
            <span className="meta">{games} total</span>
          </div>
          <div className="tblwrap">
            <div className="toolrow">
              <div className="inp">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Filter by winner or finish…"
                  aria-label="Filter games"
                />
              </div>
              <span className="upd">
                {filtered.length} of {plural(games, "game")}
              </span>
            </div>
            <table className="games">
              <thead>
                <tr>
                  <th style={{ width: 64 }}>Game</th>
                  <th style={{ width: 220 }}>Winner</th>
                  <th style={{ width: 70 }}>Ended</th>
                  <th style={{ width: 80 }}>Duration</th>
                  <th>Decided by</th>
                  <th className="r" style={{ width: 90 }}>
                    Replay
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((g) => (
                  <tr
                    key={g.n}
                    className="click"
                    onClick={() => router.push(`/results/${enc}/replay/${g.n}`)}
                  >
                    <td className="id">#{g.n}</td>
                    <td>
                      {g.draw ? (
                        <span className="st out">
                          <i />
                          Draw
                        </span>
                      ) : g.winnerName && topNames.has(g.winnerName) ? (
                        <span className="st win">
                          <i />
                          {g.winnerName}
                        </span>
                      ) : (
                        (g.winnerName ?? "—")
                      )}
                    </td>
                    <td className="mono">T{g.endedTurn}</td>
                    <td className="dur">{fmtClock(g.durationMs)}</td>
                    <td>
                    {g.decidedBy}
                    {(() => {
                      // The summary can only say who won and when; the analysis
                      // knows HOW. Only annotate the non-default methods.
                      const m = an?.games.find((x) => x.n === g.n);
                      if (!m || m.method === "combat damage / life loss" || m.method === "not recorded")
                        return null;
                      return (
                        <span className="ctanote">
                          {" "}— {m.method === "spell" ? `won by ${m.detail}` : m.method}
                        </span>
                      );
                    })()}
                  </td>
                    <td className="r">
                      <Link
                        className="bl"
                        href={`/results/${enc}/replay/${g.n}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        Watch
                      </Link>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6}>No games match “{q}”.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="note">
            “Decided by” reports the run summary’s result line — the winner and the turn the log
            ended on. Naming the final swing, drain, or poison total needs the event record, so open
            a replay for that.
          </p>
        </section>
      </div>
      <Footer right={file} />
    </>
  );
}
