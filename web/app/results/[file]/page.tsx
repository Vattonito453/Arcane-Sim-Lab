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
import { Chrome, Footer, PageDetails, type TabDef } from "@/components/Chrome";
import { api, RateLimited } from "@/lib/api";
import type { AnalysisReport, RunGameSummary, RunSummary } from "@/lib/types";
import { fmtDay, pct, plural, runDate, runTitle, stripAi } from "@/lib/format";

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
  // `raw` is optional-chained: every adapter path sets it today, but a result
  // with neither a winner nor a raw line should render as "–" rather than take
  // the whole page down with it.
  const key = g.result.winner ?? g.result.raw?.match(RE_WON_RAW)?.[1]?.trim() ?? null;
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
      : "–";
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

    // First game the leading deck actually won — target for the primary action.
    let watchGame = 1;
    for (const g of gameRows) {
      if (g.winnerName && topNames.has(g.winnerName)) {
        watchGame = g.n;
        break;
      }
    }
    return { games, baseline, rows, tops, topNames, gameRows, medTurns, rotated, watchGame };
  }, [data, file]);

  // The matchup, not the filename: "sim_20260724_094940_rotated.json" tells a
  // reader nothing. The address lives in the details disclosure at the foot.
  const title = view ? runTitle(view.rows.map((r) => r.name)) : file.replace(/\.json$/, "");
  const enc = encodeURIComponent(file);
  const when = runDate(file);

  // Real destinations now that telemetry and coaching exist — the row is
  // present on the loading and error states too, so it does not vanish mid-load.
  const tabs: TabDef[] = [
    { label: "Overview", href: `/results/${enc}`, on: true },
    { label: "Telemetry", href: `/results/${enc}/telemetry` },
    { label: "Coaching", href: `/results/${enc}/coaching` },
  ];

  if (err) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">{wait != null ? "Rate limited" : "Could not load this result"}</div>
            </div>
          </div>
          {wait != null ? (
            <p className="note">
              {err}. The engine is throttling reads. Try again in about{" "}
              <span className="mono">{wait}</span> s.
            </p>
          ) : (
            <p className="note">{err}. Check that the engine API is running, then reload.</p>
          )}
        </div>
        <Footer />
      </>
    );
  }
  if (!data || !view) {
    return (
      <>
        <Chrome tabs={tabs} />
        <div className="page">
          <div className="head">
            <div>
              <h1>{title}</h1>
              <div className="sub">Loading result…</div>
            </div>
          </div>
        </div>
        <Footer />
      </>
    );
  }

  const { rows, tops, topNames, gameRows, games, baseline, medTurns, rotated } = view;
  const top = rows[0];
  const second = rows.find((r) => !topNames.has(r.name));
  const draws = data.summary.draws;
  // Clock-cut games. They are draws too, so this qualifies the draw count
  // rather than adding to it: a pod that mostly times out reads as four decks
  // all "below an even share" at once, which is a property of the clock and
  // not of any deck.
  const timeouts = data.summary.timeouts ?? 0;
  const validity = data.validity;
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
      ? `, tied with ${tops.slice(1).map((t) => t.name).join(" and ")}`
      : second
        ? `, ${top.wins - second.wins} ${top.wins - second.wins === 1 ? "win" : "wins"} clear of ${second.name} (${pct(second.rate)})`
        : "";

  return (
    <>
      <Chrome tabs={tabs} />
      <div className="page">
        <div className="head">
          <div>
            <h1>{title}</h1>
            {/* What sizes the result: format, pod, sample, date. The result
                filename used to be the third item here — an address, and the
                only one of the five that told a reader nothing. The date
                replaces it and earns its place: four runs of this matchup are
                otherwise indistinguishable. */}
            <div className="sub">
              {String(data.meta?.format ?? "Commander")}
              <span className="sep">·</span>
              {plural(rows.length, "deck")}
              <span className="sep">·</span>
              <span className="mono">{games}</span> {rotated ? "seat-rotated " : ""}
              {games === 1 ? "game" : "games"}
              {when && (
                <>
                  <span className="sep">·</span>
                  {fmtDay(when)}
                </>
              )}
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
              {draws} {draws === 1 ? "game" : "games"} ended drawn
              {timeouts > 0 &&
                (timeouts >= draws ? (
                  <>
                    , {draws === 1 ? "and it hit" : "all of them hitting"} the
                    per-game clock rather than finishing
                  </>
                ) : (
                  <>
                    , <b>{timeouts}</b> of those because{" "}
                    {timeouts === 1 ? "it hit" : "they hit"} the per-game clock
                    rather than finishing
                  </>
                ))}
              ; the median game ran <b>{medTurns} turns</b>.
            </>
          ) : (
            <>No draws; the median game ran <b>{medTurns} turns</b>.</>
          )}
        </p>

        {validity && validity.quality !== "clean" && (
          <p className="note">
            <b>
              {validity.quality === "polluted"
                ? "These numbers are not trustworthy."
                : "Read these numbers with care."}
            </b>{" "}
            {validity.reasons.join(" ")}
          </p>
        )}

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
            <div className="l">top win rate ({top.name})</div>
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
            The marker sits at {pct(baseline, 1)}, an even share of a {rows.length}-player pod.
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
            {/* Six independent numeric columns that only mean anything side by
                side, so this one keeps its grid instead of stacking. What it
                needed was for the scroll to stop being invisible. */}
            <p className="note only-narrow">Scroll the table sideways for the full breakdown.</p>
            <div className="tblwrap">
              <table className="games">
                <thead>
                  <tr>
                    <th>Deck</th>
                    <th>Combo</th>
                    <th className="r">Assembled</th>
                    <th className="r">From draws</th>
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
                          <td colSpan={5} className="ctanote">
                            combos unknown; Spellbook was unreachable when this was analysed
                          </td>
                        </tr>,
                      ];
                    }
                    if (d.combos.length === 0) {
                      return [
                        <tr key={`${name}-none`}>
                          <td>{name}</td>
                          <td colSpan={5} className="ctanote">
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
                      // mean anything, or is the AI the bottleneck? Server-
                      // computed since v3; derive it for older payloads.
                      const reading =
                        c.reading ??
                        (c.converted_games > 0
                          ? "fired"
                          : c.assembled_games > 0
                            ? "assembled_not_fired"
                            : "not_assembled");
                      const spellPieces = c.nonpermanent_pieces ?? [];
                      return (
                        <tr key={`${name}-${c.id}`}>
                          <td>{name}</td>
                          <td
                            title={
                              c.produces.join(", ") +
                              (spellPieces.length > 0
                                ? `. ${spellPieces.join(", ")} is a spell piece: counted when cast, not from the battlefield`
                                : "")
                            }
                          >
                            {c.cards.join(" + ")}
                          </td>
                          <td className="r mono">
                            {c.assembled_games} of {c.games_played}
                            {c.median_assembled_turn != null && <> (T{c.median_assembled_turn})</>}
                          </td>
                          <td
                            className="r mono"
                            title="How many of these games raw draw odds alone predicted every library piece would be drawn by game end. Assembled above this means tutors did work; far below means pieces sat in hand or died."
                          >
                            {c.expected_drawn_games != null ? `~${c.expected_drawn_games}` : "–"}
                          </td>
                          <td className="r mono">{c.converted_games}</td>
                          <td>
                            {reading === "fired" ? (
                              <span className="st win">
                                <i />
                                AI can fire this; results meaningful
                              </span>
                            ) : reading === "assembled_not_fired" ? (
                              <span className="st warn">
                                <i />
                                assembled, never fired; win rate is a floor
                              </span>
                            ) : reading === "sample_too_small" ? (
                              <span className="st loss">
                                <i />
                                draw odds predicted ~{c.expected_drawn_games ?? 0}; too few
                                games to measure this
                              </span>
                            ) : (
                              <span className="st warn">
                                <i />
                                never assembled despite draw odds ~{c.expected_drawn_games};
                                pieces sat in hand or died
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    });
                  })}
                </tbody>
              </table>
              {/* DESIGN_SYSTEM.md requires an honesty note on inferred data. It
                  does not require 95 words of method on every visit. The caveat
                  that changes how you read the column stays inline; the method
                  moves one click away. */}
              <p className="note">
                Assembled is inferred from board reconstruction, not read from the log.
              </p>
              <PageDetails label="How these numbers are measured">
                Assembled counts games where every piece was on the battlefield at once, from board
                reconstruction, an inference rather than a read. Instant and sorcery pieces count as
                present on turns they were cast. From draws is the hypergeometric chance of
                having drawn every piece by each game&apos;s end, given cards seen (opening hand, one
                per turn cycle, plus logged effect draws; commanders are always available). Converted
                means that seat then won.
                {an && (
                  <>
                    {" "}Draw velocity:{" "}
                    {Object.entries(an.decks)
                      .filter(([, d]) => d.draws?.per_own_turn != null)
                      .map(([name, d]) => `${name} ${d.draws?.per_own_turn}/turn cycle`)
                      .join(" · ")}
                    .
                  </>
                )}
                {Object.values(an.decks).some((d) => d.combos.some((c) => c.idle_online_turns > 0)) && (
                  <>
                    {" "}Combos here sat fully online{" "}
                    <span className="mono">
                      {Object.values(an.decks).reduce(
                        (a, d) => a + d.combos.reduce((x, c) => x + c.idle_online_turns, 0), 0)}
                    </span>{" "}
                    turns without winning. Forge&apos;s AI does not pilot loops, so treat those decks&apos;
                    numbers as a floor, not a verdict.
                  </>
                )}
              </PageDetails>
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
            {/* `stackable` + the c- cell classes are the narrow-screen contract
                (globals.css): below 720px the head hides and each row reflows to
                two lines rather than hiding four of its six columns behind a
                horizontal scroll nobody discovers. */}
            <table className="games stackable">
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
                    {/* Wide: its own column. Narrow: it belongs on the title
                        line, not orphaned above it — a block-level title after
                        an inline cell starts a new line box. */}
                    <td className="id c-drop">#{g.n}</td>
                    <td className="c-title">
                      <span className="only-narrow-inline gnum">#{g.n} </span>
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
                        (g.winnerName ?? "–")
                      )}
                    </td>
                    <td className="mono c-meta">T{g.endedTurn}</td>
                    <td className="dur c-meta">{fmtClock(g.durationMs)}</td>
                    <td className="c-meta">
                    {g.decidedBy}
                    {(() => {
                      // The summary can only say who won and when; the analysis
                      // knows HOW. Only annotate the non-default methods.
                      const m = an?.games.find((x) => x.n === g.n);
                      if (!m || m.method === "combat damage / life loss" || m.method === "not recorded")
                        return null;
                      return (
                        <span className="ctanote">
                          {" ("}{m.method === "spell" ? `won by ${m.detail}` : m.method}{")"}
                        </span>
                      );
                    })()}
                  </td>
                    <td className="r c-act">
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
                    <td className="c-empty" colSpan={6}>No games match “{q}”.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="note">
            Open a replay to see what actually did the killing.
          </p>
        </section>

        <PageDetails label="Run details">
          <div>{file}</div>
          {when && <div>{when.toLocaleString()}</div>}
          <div>
            {plural(games, "game")} · {data.games.reduce((a, g) => a + g.events, 0).toLocaleString("en-US")} events
            {data.meta?.source ? ` · ${String(data.meta.source)}` : ""}
          </div>
        </PageDetails>
      </div>
      <Footer />
    </>
  );
}
